# Audi Connect CLI

A powerful command-line interface for interacting with Audi Connect services, allowing you to monitor and control your Audi vehicle remotely.

## Features

- 🚗 **Vehicle Status Monitoring** - Check battery level, mileage, lock status, location, and more
- 🔐 **Remote Control** - Lock/unlock doors, start/stop climate control, control auxiliary heating
- 🔋 **Electric Vehicle Support** - Full support for e-tron models with charging control
- 🌍 **Multi-Region Support** - Works with Audi Connect services in DE, US, CA, and CN regions
- 🛡️ **Secure Authentication** - OAuth2-based authentication with automatic token refresh
- 📊 **JSON Output** - Machine-readable JSON output for integration with other tools
- 🔄 **Throttling Protection** - Built-in protection against API rate limiting

## Prerequisites

- Python 3.8 or higher
- An active Audi Connect account
- Vehicle with Audi Connect services enabled

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/ashleigh-hopkins/audi-connect-dev.git
cd audi-connect-dev
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Clone the Audi Connect HA library

The `audi_connect_ha` library is a Home Assistant custom component, not a pip package. Clone it into the project directory:

```bash
git clone https://github.com/audiconnect/audi_connect_ha.git
```

## Configuration

### Using config.json (Recommended)

Create a `config.json` file based on the provided example:

```bash
cp config_example.json config.json
```

Edit `config.json` with your credentials:

```json
{
  "username": "your.email@example.com",
  "password": "your_password",
  "country": "DE",
  "spin": "1234",
  "api_level": 0,
  "vehicles": [
    {
      "vin": "WAUZZZ...",
      "name": "My Audi",
      "model": "Audi e-tron",
      "model_year": "2024",
      "csid": "optional_csid",
      "notes": "Main family vehicle"
    }
  ]
}
```

**Configuration parameters:**
- `username`: Your Audi Connect account email
- `password`: Your Audi Connect account password
- `country`: Your country code (DE, US, CA, or CN)
- `spin`: Your 4-digit S-PIN for security operations
- `api_level`: API level (0 for gas vehicles, 1 for e-tron/electric)
- `vehicles`: Optional array of vehicle configurations

### Using command-line arguments

Alternatively, you can provide credentials via command line:

```bash
python audi_cli.py -u your.email@example.com -p your_password -c DE --spin 1234
```

## Usage

### Basic Commands

#### List all vehicles
```bash
python audi_cli.py list-vehicles
```

#### Get vehicle status
```bash
python audi_cli.py status YOUR_VIN
```

#### Get vehicle status in JSON format
```bash
python audi_cli.py status YOUR_VIN --json
```

### Vehicle Control Commands

#### Lock/Unlock vehicle
```bash
python audi_cli.py lock YOUR_VIN
python audi_cli.py unlock YOUR_VIN
```

#### Climate control
```bash
# Start climate control with default temperature (21°C)
python audi_cli.py climate-start YOUR_VIN

# Start with specific temperature and options
python audi_cli.py climate-start YOUR_VIN --temp 22 --glass-heating

# Start with seat heating
python audi_cli.py climate-start YOUR_VIN --seat-fl --seat-fr

# Stop climate control
python audi_cli.py climate-stop YOUR_VIN
```

#### Pre-heater/Auxiliary heating (if equipped)
```bash
# Start pre-heater for 30 minutes (default)
python audi_cli.py preheater-start YOUR_VIN

# Start pre-heater for specific duration
python audi_cli.py preheater-start YOUR_VIN --duration 45

# Stop pre-heater
python audi_cli.py preheater-stop YOUR_VIN
```

#### Window heating
```bash
python audi_cli.py window-heating-start YOUR_VIN
python audi_cli.py window-heating-stop YOUR_VIN
```

### Electric Vehicle Commands

#### Charging control
```bash
# Start manual charging
python audi_cli.py charge-start YOUR_VIN

# Start timer-based charging
python audi_cli.py charge-start YOUR_VIN --timer

# Set target charge level (20-100%)
python audi_cli.py set-charge-target YOUR_VIN 80
```

### Data Commands

#### Refresh vehicle data
```bash
# Request fresh data from the vehicle
python audi_cli.py refresh-data YOUR_VIN
```

#### Get trip data
```bash
# View trip statistics and consumption data
python audi_cli.py trip-data YOUR_VIN
```

### Advanced Usage

#### Debug mode
```bash
python audi_cli.py --debug status YOUR_VIN
```

#### Raw API response
```bash
python audi_cli.py status YOUR_VIN --raw
```


## Examples

For more examples and advanced usage, check the command-line help:

```bash
python audi_cli.py --help
```

## Security Notes

- **Never commit credentials**: Always use `config.json` (which is gitignored) or environment variables
- **S-PIN Security**: Your S-PIN is required for security-critical operations like lock/unlock
- **Token Storage**: Authentication tokens are stored temporarily in memory only
- **Rate Limiting**: The CLI includes built-in throttling protection to prevent account suspension

## Troubleshooting

### Common Issues

1. **Authentication failures**
   - Verify your credentials are correct
   - Check if your account is active on myAudi website
   - Ensure you're using the correct country code

2. **Missing vehicle data**
   - Some features may not be available for all vehicles
   - Check API level (0 for gas, 1 for electric vehicles)
   - Ensure vehicle has active Audi Connect subscription

3. **Rate limiting errors**
   - Wait at least 15 minutes between requests
   - Use the built-in throttling protection
   - Avoid excessive API calls

4. **SSL/Certificate errors**
   - Update your Python certificates: `pip install --upgrade certifi`
   - Check your system time is correct

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is provided as-is for educational and personal use. Use at your own risk.

## Disclaimer

This is an unofficial tool and is not affiliated with, endorsed by, or connected to Audi AG or Volkswagen Group. Use of this tool is at your own risk, and you are responsible for complying with any terms of service or usage agreements with Audi Connect services.

## Acknowledgments

- Based on the [audi_connect_ha](https://github.com/audiconnect/audi_connect_ha) Home Assistant integration
- Thanks to the Audi Connect community for reverse engineering efforts
