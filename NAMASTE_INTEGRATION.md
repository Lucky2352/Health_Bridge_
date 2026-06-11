# NAMASTE API Integration Guide

## Overview
This project now supports both official NAMASTE API integration and CSV fallback for demo purposes, making it jury-ready and production-ready.

## Features
- **Official NAMASTE API**: Connects to https://namaste-ayush.gov.in/ when API key is available
- **CSV Fallback**: Uses local demo data when API is unavailable or not configured
- **Seamless Integration**: Automatic fallback with source indication
- **Status Monitoring**: Built-in endpoint to check service health

## Configuration

### 1. Environment Variables
Create a `.env` file or set environment variables:

```bash
# For production with official API
set NAMASTE_API_KEY=your_official_api_key_here

# For demo/testing (no API key needed)
# System will automatically use CSV fallback
```

### 2. Getting Official API Key
1. Visit https://namaste-ayush.gov.in/
2. Register for API access
3. Obtain your API key from the Ministry of AYUSH
4. Set the `NAMASTE_API_KEY` environment variable

## Usage

### Search Endpoint
```
GET /search?q=fever
```

**Response with API:**
```json
{
  "namaste": [...],
  "namaste_source": "api",
  "namaste_message": "Results from official NAMASTE API",
  "icd11": [...]
}
```

**Response with CSV Fallback:**
```json
{
  "namaste": [...],
  "namaste_source": "csv",
  "namaste_message": "CSV fallback (demo data)",
  "icd11": [...]
}
```

### Status Endpoint
```
GET /namaste/status
```

**Response:**
```json
{
  "api_configured": true,
  "api_key_preview": "abc123...",
  "csv_fallback_available": true,
  "service_ready": true,
  "last_test": {
    "query": "fever",
    "source": "api",
    "results_count": 5,
    "message": "Results from official NAMASTE API"
  }
}
```

## Testing

### Run Test Script
```bash
python test_namaste_service.py
```

This will test both scenarios:
- CSV fallback (without API key)
- API integration (if API key is configured)

### Manual Testing
1. **Without API key**: Search should show "Demo Data" badge
2. **With API key**: Search should show "Official API" badge

## Implementation Details

### Service Architecture
```
utils/namaste_service.py
├── NAMASTEService class
├── API integration with requests
├── CSV fallback mechanism
└── Error handling and logging
```

### Integration Points
- `app.py`: Main search endpoint updated
- `fhir_conceptmap.py`: ConceptMapper updated for new service
- `templates/search.html`: UI shows source information

### Error Handling
- Network timeouts (10 seconds)
- API authentication failures
- Malformed responses
- Graceful fallback to CSV data

## Production Deployment

### With Official API Key
1. Set `NAMASTE_API_KEY` environment variable
2. Deploy application
3. Verify `/namaste/status` shows `"api_configured": true`

### Demo/Development Mode
1. Ensure `namaste_codes.csv` exists
2. Deploy without API key
3. System automatically uses CSV fallback

## Benefits for Jury Presentation

### ✅ Immediate Demo Capability
- Works without any external dependencies
- Shows real AYUSH medical codes
- Demonstrates full functionality

### ✅ Production Readiness
- Official API integration ready
- Proper error handling and fallbacks
- Status monitoring and health checks

### ✅ Professional Implementation
- Clean separation of concerns
- Comprehensive logging
- Standard REST API patterns

## Troubleshooting

### Common Issues
1. **No results**: Check if CSV file exists or API key is valid
2. **Slow responses**: API timeout is set to 10 seconds
3. **Source shows "csv"**: API key not configured or API unavailable

### Debug Commands
```bash
# Check service status
curl http://localhost:8000/namaste/status

# Test search
curl "http://localhost:8000/search?q=fever"

# Run test script
python test_namaste_service.py
```

## Future Enhancements
- API response caching
- Multiple API endpoint support
- Advanced error recovery
- Performance monitoring