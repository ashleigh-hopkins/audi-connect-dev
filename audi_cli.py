#!/usr/bin/env python3
"""
Audi Connect CLI Tool

A command-line interface to interact with Audi Connect vehicles directly,
bypassing Home Assistant. Provides full access to vehicle commands, controls,
and data with raw API response analysis capabilities.

Usage:
    python audi_cli.py --help
"""

import asyncio
import json
import logging
import argparse
import os
import time
from typing import Optional, Any, Dict
import aiohttp

# Import the Audi Connect components
# Add the audi_connect_ha repository to the path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'audi_connect_ha'))

from custom_components.audiconnect.audi_connect_account import AudiConnectAccount

# Setup logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class SafeAudiConnectAccount(AudiConnectAccount):
    """Extended AudiConnectAccount that doesn't retry on throttling errors."""
    
    async def login(self):
        """Override login to stop retrying on throttling errors."""
        for i in range(self._connect_retries):
            try:
                self._loggedin = await self.try_login(i == self._connect_retries - 1)
                if self._loggedin is True:
                    self._logintime = time.time()
                    break
            except Exception as e:
                error_msg = str(e)
                # Check for throttling errors
                if 'throttled' in error_msg.lower() or 'error=login.error.throttled' in error_msg:
                    logger.error("LOGIN: Account is throttled. Please wait before trying again.")
                    logger.error(f"Error message: {error_msg}")
                    # Don't retry on throttling
                    return False
                # For other errors, continue with normal retry logic
                if i < self._connect_retries - 1:
                    logger.error(
                        "LOGIN: Login to Audi service failed, trying again in %d seconds",
                        self._connect_delay
                    )
                    await asyncio.sleep(self._connect_delay)
                else:
                    logger.error(
                        "LOGIN: Failed to log in to the Audi service: %s."
                        "You may need to open the myAudi app, or log in via a web browser, to accept updated terms and conditions.",
                        error_msg,
                    )
        return self._loggedin
    
    async def try_login(self, logError):
        """Override to propagate exceptions for throttling detection."""
        try:
            logger.debug("LOGIN: Requesting login to Audi service...")
            await self._audi_service.login(self._username, self._password, False)
            logger.debug("LOGIN: Login to Audi service successful")
            return True
        except Exception as exception:
            # Propagate the exception so we can check for throttling
            if 'throttled' in str(exception).lower():
                raise exception
            if logError is True:
                logger.error(
                    "LOGIN: Failed to log in to the Audi service: %s."
                    "You may need to open the myAudi app, or log in via a web browser, to accept updated terms and conditions.",
                    str(exception),
                )
            return False


def load_config(config_file: str = "config.json") -> Optional[Dict[str, Any]]:
    """Load configuration from file if it exists."""
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load config file: {e}")
    return None


class AudiCLI:
    """Main CLI class for Audi Connect operations."""

    def __init__(
        self,
        username: str,
        password: str,
        country: str,
        spin: Optional[str] = None,
        api_level: int = 0,
        debug: bool = False,
    ):
        self.username = username
        self.password = password
        self.country = country
        self.spin = spin
        self.api_level = api_level
        self.session = None
        self.account = None
        self.debug = debug

        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.getLogger("custom_components.audiconnect").setLevel(logging.DEBUG)

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        self.account = SafeAudiConnectAccount(
            session=self.session,
            username=self.username,
            password=self.password,
            country=self.country,
            spin=self.spin,
            api_level=self.api_level,
        )
        await self.account.login()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    def print_json(self, data: Any, title: str = ""):
        """Pretty print JSON data."""
        if title:
            print(f"\n=== {title} ===")
        print(json.dumps(data, indent=2, sort_keys=True, default=str))

    def print_vehicle_summary(self, vehicle):
        """Print a summary of vehicle information."""
        print("\n=== Vehicle Summary ===")
        print(f"VIN: {vehicle.vin}")
        print(f"Title: {vehicle.title}")
        print(f"Model: {vehicle.model}")
        print(f"Model Year: {vehicle.model_year}")
        print(f"CSID: {vehicle.csid}")

    async def list_vehicles(self, raw: bool = False, json_output: bool = False):
        """List all vehicles associated with the account."""
        if not json_output:
            print("Fetching vehicle list...")
        await self.account.update(vinlist=None)

        if not self.account._vehicles:
            if json_output:
                print(json.dumps({"vehicles": [], "error": "No vehicles found"}))
            else:
                print("No vehicles found.")
            return

        if json_output:
            # Return pure JSON for programmatic use
            vehicles_data = []
            for vehicle in self.account._vehicles:
                vehicle_data = {
                    "vin": vehicle.vin,
                    "title": vehicle.title,
                    "model": vehicle.model,
                    "model_year": vehicle.model_year,
                    "csid": vehicle.csid,
                    "fields": vehicle._vehicle.fields,
                    "state": vehicle._vehicle.state,
                }
                vehicles_data.append(vehicle_data)
            print(json.dumps({"vehicles": vehicles_data}, indent=2, default=str))
        else:
            for i, vehicle in enumerate(self.account._vehicles):
                print(f"\n--- Vehicle {i + 1} ---")
                self.print_vehicle_summary(vehicle)

                if raw:
                    # Print raw vehicle data
                    raw_data = {
                        "fields": vehicle._vehicle.fields,
                        "state": vehicle._vehicle.state,
                    }
                    self.print_json(raw_data, f"Raw Data for {vehicle.vin}")

    async def get_vehicle_status(self, vin: str, raw: bool = False, json_output: bool = False):
        """Get comprehensive vehicle status."""
        if not json_output:
            print(f"Fetching status for VIN: {vin}")
        await self.account.update(vinlist=[vin.lower()])

        vehicle = self._find_vehicle_silent(vin) if json_output else self._find_vehicle(vin)
        if not vehicle:
            if json_output:
                print(json.dumps({"error": f"Vehicle with VIN {vin} not found"}))
            return

        if json_output:
            # Return pure JSON for programmatic use
            status_data = {
                "vin": vehicle.vin,
                "title": vehicle.title,
                "model": vehicle.model,
                "model_year": vehicle.model_year,
                "csid": vehicle.csid,
                "last_update": str(vehicle.last_update_time) if vehicle.last_update_time_supported else None,
                "mileage": vehicle.mileage if vehicle.mileage_supported else None,
                "range": vehicle.range if vehicle.range_supported else None,
                "electric_range": vehicle.hybrid_range if vehicle.hybrid_range_supported else None,
                "battery_level": vehicle.state_of_charge if vehicle.state_of_charge_supported else None,
                "target_charge": vehicle.target_state_of_charge if vehicle.target_state_of_charge_supported else None,
                "charging_state": vehicle.charging_state if vehicle.charging_state_supported else None,
                "plug_connected": vehicle.plug_state if vehicle.plug_state_supported else None,
                "climate_state": vehicle.climatisation_state if vehicle.climatisation_state_supported else None,
                "doors_locked": vehicle.doors_trunk_status == "Locked" if vehicle.doors_trunk_status_supported else None,
                "windows_closed": not vehicle.any_window_open if vehicle.any_window_open_supported else None,
                "position": vehicle.position if vehicle.position_supported else None,
                "fields": vehicle._vehicle.fields,
                "state": vehicle._vehicle.state,
            }
            print(json.dumps(status_data, indent=2, default=str))
        else:
            self.print_vehicle_summary(vehicle)

            # Print organized status information
            self._print_vehicle_status(vehicle)

            if raw:
                raw_data = {
                    "fields": vehicle._vehicle.fields,
                    "state": vehicle._vehicle.state,
                }
                self.print_json(raw_data, "Raw Vehicle Data")

    def _find_vehicle(self, vin: str):
        """Find vehicle by VIN."""
        vehicle = next(
            (v for v in self.account._vehicles if v.vin == vin.lower()), None
        )
        if not vehicle:
            print(f"Vehicle with VIN {vin} not found.")
            print("Available VINs:")
            for v in self.account._vehicles:
                print(f"  - {v.vin}")
        return vehicle
    
    def _find_vehicle_silent(self, vin: str):
        """Find vehicle by VIN without printing errors."""
        return next(
            (v for v in self.account._vehicles if v.vin == vin.lower()), None
        )

    def _print_vehicle_status(self, vehicle):
        """Print organized vehicle status information."""

        print("\n=== Vehicle Status ===")

        # Basic Info
        if vehicle.last_update_time_supported:
            print(f"Last Update: {vehicle.last_update_time}")
        if vehicle.mileage_supported:
            print(f"Mileage: {vehicle.mileage:,} km")
        if vehicle.range_supported:
            print(f"Total Range: {vehicle.range} km")
        if vehicle.hybrid_range_supported:
            print(f"Electric Range: {vehicle.hybrid_range} km")
        if vehicle.primary_engine_range_supported and vehicle.secondary_engine_range_supported:
            print(f"Primary Engine Range: {vehicle.primary_engine_range} km")
            print(f"Secondary Engine Range: {vehicle.secondary_engine_range} km")

        # Position
        if vehicle.position_supported:
            pos = vehicle.position
            print(f"\n--- Location ---")
            print(f"Position: Lat {pos['latitude']:.6f}, Lon {pos['longitude']:.6f}")
            if pos.get("parktime"):
                print(f"Parked Since: {pos['parktime']}")

        # Electric Vehicle Info
        if vehicle.car_type_supported and vehicle.car_type in ["electric", "hybrid"]:
            print("\n--- Electric Vehicle ---")
            if vehicle.state_of_charge_supported:
                print(f"Battery Level: {vehicle.state_of_charge}%")
            if vehicle.target_state_of_charge_supported:
                print(f"Target Charge: {vehicle.target_state_of_charge}%")
            if vehicle.plug_state_supported:
                plug_connected = vehicle.plug_state
                print(f"Plug Connected: {'Yes' if plug_connected else 'No'}")
            if vehicle.plug_lock_state_supported:
                plug_locked = vehicle.plug_lock_state
                print(f"Plug Unlocked: {'Yes' if plug_locked else 'No'}")
            if vehicle.plug_led_color_supported:
                print(f"Plug LED Color: {vehicle.plug_led_color}")
            if vehicle.external_power_supported:
                print(f"External Power: {vehicle.external_power}")
            if vehicle.charging_state_supported:
                print(f"Charging State: {vehicle.charging_state}")
            if vehicle.charging_mode_supported:
                print(f"Charging Mode: {vehicle.charging_mode}")
            if vehicle.charging_power_supported and vehicle.charging_power > 0:
                print(f"Charging Power: {vehicle.charging_power:.1f} kW")
            if vehicle.actual_charge_rate_supported and vehicle.actual_charge_rate > 0:
                print(f"Charge Rate: {vehicle.actual_charge_rate} {vehicle.actual_charge_rate_unit}")
            if vehicle.remaining_charging_time_supported and vehicle.remaining_charging_time > 0:
                print(f"Time to Full: {vehicle.remaining_charging_time} min")
                if vehicle.charging_complete_time:
                    print(f"Charge Complete: {vehicle.charging_complete_time}")
        
        # Fuel Vehicle Info
        if vehicle.tank_level_supported:
            print("\n--- Fuel ---")
            print(f"Fuel Level: {vehicle.tank_level}%")

        # Climate
        print("\n--- Climate ---")
        if vehicle.climatisation_state_supported:
            print(f"Climate Control: {vehicle.climatisation_state}")
        if vehicle.remaining_climatisation_time_supported and vehicle.remaining_climatisation_time > 0:
            print(f"Climate Time Remaining: {vehicle.remaining_climatisation_time} min")
        if vehicle.outdoor_temperature_supported:
            print(f"Outdoor Temperature: {vehicle.outdoor_temperature}°C")
        if vehicle.glass_surface_heating_supported:
            print(f"Glass Heating: {'Active' if vehicle.glass_surface_heating else 'Inactive'}")
        if vehicle.preheater_active_supported:
            print(f"Pre-heater: {'Active' if vehicle.preheater_active else 'Inactive'}")
            if vehicle.preheater_active and vehicle.preheater_remaining_supported:
                print(f"Pre-heater Time Remaining: {vehicle.preheater_remaining} min")

        # Security
        print("\n--- Security & Access ---")
        if vehicle.doors_trunk_status_supported:
            print(f"Doors/Trunk: {vehicle.doors_trunk_status}")
            # Detailed door status
            if vehicle.any_door_open:
                doors_open = []
                if vehicle.left_front_door_open_supported and vehicle.left_front_door_open:
                    doors_open.append("Front Left")
                if vehicle.right_front_door_open_supported and vehicle.right_front_door_open:
                    doors_open.append("Front Right")
                if vehicle.left_rear_door_open_supported and vehicle.left_rear_door_open:
                    doors_open.append("Rear Left")
                if vehicle.right_rear_door_open_supported and vehicle.right_rear_door_open:
                    doors_open.append("Rear Right")
                if doors_open:
                    print(f"  Open Doors: {', '.join(doors_open)}")
            if vehicle.trunk_open_supported and vehicle.trunk_open:
                print(f"  Trunk: Open")
            if vehicle.hood_open_supported and vehicle.hood_open:
                print(f"  Hood: Open")
        
        if vehicle.any_window_open_supported:
            print(f"Windows: {'Open' if vehicle.any_window_open else 'Closed'}")
            if vehicle.any_window_open:
                windows_open = []
                if vehicle.left_front_window_open_supported and vehicle.left_front_window_open:
                    windows_open.append("Front Left")
                if vehicle.right_front_window_open_supported and vehicle.right_front_window_open:
                    windows_open.append("Front Right")
                if vehicle.left_rear_window_open_supported and vehicle.left_rear_window_open:
                    windows_open.append("Rear Left")
                if vehicle.right_rear_window_open_supported and vehicle.right_rear_window_open:
                    windows_open.append("Rear Right")
                if vehicle.sun_roof_supported and vehicle.sun_roof:
                    windows_open.append("Sunroof")
                if windows_open:
                    print(f"  Open Windows: {', '.join(windows_open)}")
        
        if vehicle.parking_light_supported:
            print(f"Parking Lights: {'On' if vehicle.parking_light else 'Off'}")

        # Maintenance
        maintenance_items = []
        if vehicle.service_inspection_time_supported:
            maintenance_items.append(f"Service in {vehicle.service_inspection_time} days")
        if vehicle.service_inspection_distance_supported:
            maintenance_items.append(f"Service in {vehicle.service_inspection_distance:,} km")
        if vehicle.oil_change_time_supported:
            maintenance_items.append(f"Oil change in {vehicle.oil_change_time} days")
        if vehicle.oil_change_distance_supported:
            maintenance_items.append(f"Oil change in {vehicle.oil_change_distance:,} km")
        if vehicle.service_adblue_distance_supported:
            maintenance_items.append(f"AdBlue range: {vehicle.service_adblue_distance:,} km")
        
        if maintenance_items:
            print("\n--- Maintenance ---")
            for item in maintenance_items:
                print(f"  {item}")
        
        if vehicle.oil_level_supported:
            print(f"Oil Level: {vehicle.oil_level:.1f}%")
        elif vehicle.oil_level_binary_supported:
            print(f"Oil Level: {'OK' if not vehicle.oil_level_binary else 'Low'}")
        
        # Engine Type
        if vehicle.primary_engine_type_supported or vehicle.secondary_engine_type_supported:
            print("\n--- Drivetrain ---")
            if vehicle.primary_engine_type_supported:
                print(f"Primary Engine: {vehicle.primary_engine_type}")
            if vehicle.secondary_engine_type_supported:
                print(f"Secondary Engine: {vehicle.secondary_engine_type}")
            if vehicle.car_type_supported:
                print(f"Vehicle Type: {vehicle.car_type.capitalize()}")

    async def lock_vehicle(self, vin: str):
        """Lock the vehicle."""
        if not self.spin:
            print("ERROR: S-PIN is required for lock operations")
            return False

        print(f"Locking vehicle {vin}...")
        result = await self.account.set_vehicle_lock(vin, True)
        if result:
            print("Vehicle locked successfully")
        else:
            print("Failed to lock vehicle")
        return result

    async def unlock_vehicle(self, vin: str):
        """Unlock the vehicle."""
        if not self.spin:
            print("ERROR: S-PIN is required for unlock operations")
            return False

        print(f"Unlocking vehicle {vin}...")
        result = await self.account.set_vehicle_lock(vin, False)
        if result:
            print("Vehicle unlocked successfully")
        else:
            print("Failed to unlock vehicle")
        return result

    async def start_climate(
        self,
        vin: str,
        temp_c: int = 21,
        temp_f: Optional[int] = None,
        glass_heating: bool = False,
        seat_fl: bool = False,
        seat_fr: bool = False,
        seat_rl: bool = False,
        seat_rr: bool = False,
        climatisation_at_unlock: bool = False,
    ):
        """Start climate control with advanced settings."""
        print(f"Starting climate control for {vin}...")
        print(f"Temperature: {temp_c}°C")
        print(f"Glass Heating: {glass_heating}")
        print(f"Seat Heating - FL:{seat_fl} FR:{seat_fr} RL:{seat_rl} RR:{seat_rr}")
        print(f"Climatisation at Unlock: {climatisation_at_unlock}")

        result = await self.account.start_climate_control(
            vin,
            temp_f,
            temp_c,
            glass_heating,
            seat_fl,
            seat_fr,
            seat_rl,
            seat_rr,
            climatisation_at_unlock,
        )

        if result:
            print("Climate control started successfully")
        else:
            print("Failed to start climate control")
        return result

    async def stop_climate(self, vin: str):
        """Stop climate control."""
        print(f"Stopping climate control for {vin}...")
        result = await self.account.set_vehicle_climatisation(vin, False)
        if result:
            print("Climate control stopped successfully")
        else:
            print("Failed to stop climate control")
        return result

    async def start_charging(self, vin: str, timer: bool = False):
        """Start battery charging."""
        print(f"Starting {'timer' if timer else 'manual'} charging for {vin}...")
        result = await self.account.set_battery_charger(vin, True, timer)
        if result:
            print("Charging started successfully")
        else:
            print("Failed to start charging")
        return result

    async def set_charge_target(self, vin: str, target_soc: int):
        """Set the target state of charge (battery percentage)."""
        if not (20 <= target_soc <= 100):
            print("ERROR: Target charge must be between 20% and 100%")
            return False

        print(f"Setting target charge to {target_soc}% for {vin}...")
        result = await self.account.set_target_state_of_charge(vin, target_soc)
        if result:
            print(f"Target charge set to {target_soc}% successfully")
        else:
            print("Failed to set target charge")
        return result


    async def start_preheater(self, vin: str, duration: int = 30):
        """Start pre-heater."""
        if not self.spin:
            print("ERROR: S-PIN is required for pre-heater operations")
            return False

        print(f"Starting pre-heater for {vin} for {duration} minutes...")
        result = await self.account.set_vehicle_pre_heater(vin, True, duration=duration)
        if result:
            print("Pre-heater started successfully")
        else:
            print("Failed to start pre-heater")
        return result

    async def stop_preheater(self, vin: str):
        """Stop pre-heater."""
        if not self.spin:
            print("ERROR: S-PIN is required for pre-heater operations")
            return False

        print(f"Stopping pre-heater for {vin}...")
        result = await self.account.set_vehicle_pre_heater(vin, False)
        if result:
            print("Pre-heater stopped successfully")
        else:
            print("Failed to stop pre-heater")
        return result

    async def start_window_heating(self, vin: str):
        """Start window heating."""
        print(f"Starting window heating for {vin}...")
        result = await self.account.set_vehicle_window_heating(vin, True)
        if result:
            print("Window heating started successfully")
        else:
            print("Failed to start window heating")
        return result

    async def stop_window_heating(self, vin: str):
        """Stop window heating."""
        print(f"Stopping window heating for {vin}...")
        result = await self.account.set_vehicle_window_heating(vin, False)
        if result:
            print("Window heating stopped successfully")
        else:
            print("Failed to stop window heating")
        return result

    async def refresh_data(self, vin: str):
        """Request fresh vehicle data from the vehicle."""
        print(f"Requesting fresh data from vehicle {vin}...")
        result = await self.account.refresh_vehicle_data(vin)

        if result is True:
            print("Data refresh initiated successfully")
        elif result == "disabled":
            print("Data refresh is disabled for this vehicle")
        else:
            print("Failed to refresh vehicle data")
        return result

    async def get_trip_data(self, vin: str):
        """Get trip data for the vehicle."""
        print(f"Fetching trip data for {vin}...")
        await self.account.update(vinlist=[vin.lower()])

        vehicle = self._find_vehicle(vin)
        if not vehicle:
            return

        # Print trip data
        if vehicle.shortterm_current_supported:
            print("\n=== Short Term Current Trip ===")
            trip = vehicle.shortterm_current
            self._print_trip_data(trip)

        if vehicle.shortterm_reset_supported:
            print("\n=== Short Term Reset Trip ===")
            trip = vehicle.shortterm_reset
            self._print_trip_data(trip)

        if vehicle.longterm_current_supported:
            print("\n=== Long Term Current Trip ===")
            trip = vehicle.longterm_current
            self._print_trip_data(trip)

        if vehicle.longterm_reset_supported:
            print("\n=== Long Term Reset Trip ===")
            trip = vehicle.longterm_reset
            self._print_trip_data(trip)
    

    def _print_trip_data(self, trip):
        """Print trip data information."""
        if not trip:
            print("No trip data available")
            return

        print(f"Trip ID: {trip.get('tripID', 'N/A')}")
        print(f"Mileage: {trip.get('mileage', 'N/A')} km")
        print(f"Start Mileage: {trip.get('startMileage', 'N/A')} km")
        print(f"Average Speed: {trip.get('averageSpeed', 'N/A')} km/h")
        print(f"Travel Time: {trip.get('traveltime', 'N/A')} min")
        if trip.get("averageFuelConsumption"):
            print(f"Avg Fuel Consumption: {trip['averageFuelConsumption']:.1f} L/100km")
        if trip.get("averageElectricEngineConsumption"):
            print(
                f"Avg Electric Consumption: {trip['averageElectricEngineConsumption']:.1f} kWh/100km"
            )
        print(f"Zero Emission Distance: {trip.get('zeroEmissionDistance', 'N/A')} km")
        if trip.get("timestamp"):
            print(f"Timestamp: {trip['timestamp']}")


def create_parser():
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Audi Connect CLI - Direct vehicle control and monitoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using config.json (default)
  python audi_cli.py list-vehicles
  python audi_cli.py status wauzzzfz8rp006234
  
  # Using command-line credentials
  python audi_cli.py -u user@email.com -p password -c DE list-vehicles

  # Get vehicle status with raw API data
  python audi_cli.py status wauzzzfz8rp006234 --raw

  # Lock vehicle (requires S-PIN)
  python audi_cli.py lock wauzzzfz8rp006234

  # Start climate control
  python audi_cli.py climate-start wauzzzfz8rp006234 --temp 22 --glass-heating
        """,
    )

    # Authentication arguments
    parser.add_argument(
        "-u", "--username", help="Audi Connect username (email). If not provided, uses config.json"
    )
    parser.add_argument("-p", "--password", help="Audi Connect password. If not provided, uses config.json")
    parser.add_argument(
        "-c",
        "--country",
        choices=["DE", "US", "CA", "CN"],
        help="Country code. If not provided, uses config.json",
    )
    parser.add_argument("--spin", help="Security PIN for vehicle actions. If not provided, uses config.json")
    parser.add_argument(
        "--api-level", type=int, choices=[0, 1], help="API level (0 or 1). If not provided, uses config.json"
    )
    parser.add_argument("--config", default="config.json", help="Path to config file (default: config.json)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    # Commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List vehicles
    list_parser = subparsers.add_parser("list-vehicles", help="List all vehicles")
    list_parser.add_argument("--raw", action="store_true", help="Show raw API data")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON for programmatic use")

    # Vehicle status
    status_parser = subparsers.add_parser("status", help="Get vehicle status")
    status_parser.add_argument("vin", help="Vehicle VIN")
    status_parser.add_argument("--raw", action="store_true", help="Show raw API data")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON for programmatic use")

    # Lock/Unlock
    lock_parser = subparsers.add_parser("lock", help="Lock vehicle (requires S-PIN)")
    lock_parser.add_argument("vin", help="Vehicle VIN")

    unlock_parser = subparsers.add_parser(
        "unlock", help="Unlock vehicle (requires S-PIN)"
    )
    unlock_parser.add_argument("vin", help="Vehicle VIN")

    # Climate control
    climate_start_parser = subparsers.add_parser(
        "climate-start", help="Start climate control"
    )
    climate_start_parser.add_argument("vin", help="Vehicle VIN")
    climate_start_parser.add_argument(
        "--temp", type=int, default=21, help="Temperature in Celsius"
    )
    climate_start_parser.add_argument(
        "--temp-f", type=int, help="Temperature in Fahrenheit"
    )
    climate_start_parser.add_argument(
        "--glass-heating", action="store_true", help="Enable glass heating"
    )
    climate_start_parser.add_argument(
        "--seat-fl", action="store_true", help="Front left seat heating"
    )
    climate_start_parser.add_argument(
        "--seat-fr", action="store_true", help="Front right seat heating"
    )
    climate_start_parser.add_argument(
        "--seat-rl", action="store_true", help="Rear left seat heating"
    )
    climate_start_parser.add_argument(
        "--seat-rr", action="store_true", help="Rear right seat heating"
    )
    climate_start_parser.add_argument(
        "--climatisation-at-unlock",
        action="store_true",
        help="Enable climate control to start when vehicle is unlocked",
    )

    climate_stop_parser = subparsers.add_parser(
        "climate-stop", help="Stop climate control"
    )
    climate_stop_parser.add_argument("vin", help="Vehicle VIN")

    # Charging
    charge_start_parser = subparsers.add_parser("charge-start", help="Start charging")
    charge_start_parser.add_argument("vin", help="Vehicle VIN")
    charge_start_parser.add_argument(
        "--timer", action="store_true", help="Start timer charging"
    )

    charge_target_parser = subparsers.add_parser(
        "set-charge-target", help="Set target state of charge"
    )
    charge_target_parser.add_argument("vin", help="Vehicle VIN")
    charge_target_parser.add_argument(
        "target", type=int, help="Target charge percentage (20-100)"
    )


    # Pre-heater
    preheater_start_parser = subparsers.add_parser(
        "preheater-start", help="Start pre-heater (requires S-PIN)"
    )
    preheater_start_parser.add_argument("vin", help="Vehicle VIN")
    preheater_start_parser.add_argument(
        "--duration", type=int, default=30, help="Duration in minutes"
    )

    preheater_stop_parser = subparsers.add_parser(
        "preheater-stop", help="Stop pre-heater (requires S-PIN)"
    )
    preheater_stop_parser.add_argument("vin", help="Vehicle VIN")

    # Window heating
    window_start_parser = subparsers.add_parser(
        "window-heating-start", help="Start window heating"
    )
    window_start_parser.add_argument("vin", help="Vehicle VIN")

    window_stop_parser = subparsers.add_parser(
        "window-heating-stop", help="Stop window heating"
    )
    window_stop_parser.add_argument("vin", help="Vehicle VIN")

    # Data refresh
    refresh_parser = subparsers.add_parser(
        "refresh-data", help="Request fresh data from vehicle"
    )
    refresh_parser.add_argument("vin", help="Vehicle VIN")

    # Trip data
    trip_parser = subparsers.add_parser("trip-data", help="Get trip data")
    trip_parser.add_argument("vin", help="Vehicle VIN")
    

    return parser


async def main():
    """Main CLI function."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Load config file if available
    config = load_config(args.config) if hasattr(args, 'config') else load_config()
    
    # Merge command-line arguments with config file values
    username = args.username if hasattr(args, 'username') and args.username else (config.get('username') if config else None)
    password = args.password if hasattr(args, 'password') and args.password else (config.get('password') if config else None)
    country = args.country if hasattr(args, 'country') and args.country else (config.get('country') if config else None)
    spin = args.spin if hasattr(args, 'spin') and args.spin else (config.get('spin') if config else None)
    api_level = args.api_level if hasattr(args, 'api_level') and args.api_level is not None else (config.get('api_level', 0) if config else 0)
    
    # Check if we have required credentials
    if not username or not password or not country:
        print("ERROR: Missing required credentials. Please provide username, password, and country")
        print("       either via command-line arguments or in config.json")
        parser.print_help()
        return
    
    # Show config source for debugging
    if args.debug:
        print(f"Using config from: {'command-line' if args.username else 'config.json'}")
        print(f"Username: {username}")
        print(f"Country: {country}")
        print(f"API Level: {api_level}")
        print(f"S-PIN configured: {'Yes' if spin else 'No'}")
        print()

    try:
        async with AudiCLI(
            username=username,
            password=password,
            country=country,
            spin=spin,
            api_level=api_level,
            debug=args.debug,
        ) as cli:
            # Route commands
            if args.command == "list-vehicles":
                json_output = getattr(args, 'json', False)
                await cli.list_vehicles(raw=args.raw, json_output=json_output)

            elif args.command == "status":
                json_output = getattr(args, 'json', False)
                await cli.get_vehicle_status(args.vin, raw=args.raw, json_output=json_output)

            elif args.command == "lock":
                await cli.lock_vehicle(args.vin)

            elif args.command == "unlock":
                await cli.unlock_vehicle(args.vin)

            elif args.command == "climate-start":
                await cli.start_climate(
                    args.vin,
                    args.temp,
                    args.temp_f,
                    args.glass_heating,
                    args.seat_fl,
                    args.seat_fr,
                    args.seat_rl,
                    args.seat_rr,
                    args.climatisation_at_unlock
                    if hasattr(args, "climatisation_at_unlock")
                    else False,
                )

            elif args.command == "climate-stop":
                await cli.stop_climate(args.vin)

            elif args.command == "charge-start":
                await cli.start_charging(args.vin, args.timer)

            elif args.command == "set-charge-target":
                await cli.set_charge_target(args.vin, args.target)


            elif args.command == "preheater-start":
                await cli.start_preheater(args.vin, args.duration)

            elif args.command == "preheater-stop":
                await cli.stop_preheater(args.vin)

            elif args.command == "window-heating-start":
                await cli.start_window_heating(args.vin)

            elif args.command == "window-heating-stop":
                await cli.stop_window_heating(args.vin)

            elif args.command == "refresh-data":
                await cli.refresh_data(args.vin)

            elif args.command == "trip-data":
                await cli.get_trip_data(args.vin)

            else:
                print(f"Unknown command: {args.command}")
                parser.print_help()

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
