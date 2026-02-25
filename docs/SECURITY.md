# Security Guidelines

## Overview
This document outlines the security measures implemented in ReviewInsightEngine.

## Authentication

### Order ID Validation
- Order IDs are validated against database and static list
- Input sanitization prevents injection attacks
- Format validation: alphanumeric, hyphens, underscores only
- Length constraints: 3-50 characters

### Session Management
- Configurable session timeout (default: 30 minutes)
- Session data stored securely
- No sensitive data in client-side storage

## Rate Limiting

### Implementation
- Token bucket algorithm
- Per-client tracking by IP address
- Configurable limits (default: 60 requests/minute)
- Proper HTTP 429 responses with Retry-After headers

### Endpoints Protected
- `/api/auth` - Authentication attempts
- `/api/upload` - File uploads
- `/api/analyze` - Analysis requests
- `/api/compare` - Comparison requests

## Input Validation

### File Upload Security
- Extension whitelist: `.csv`, `.xlsx`, `.xls`
- File size limits (default: 50MB)
- Content validation before processing
- Malformed file detection

### Data Validation
- Column name validation
- Row consistency checks
- Duplicate detection
- Null byte removal from text

### Order ID Validation
- Format validation
- Length constraints
- Character whitelist
- Normalization (uppercase, trimmed)

## API Security

### Error Handling
- No sensitive data in error messages
- Stack traces logged, not exposed
- Generic error messages to clients
- Detailed logging for debugging

### Headers
- Proper CORS configuration
- Security headers recommended:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`

## Configuration Security

### Environment Variables
- Secrets stored in `.env` (not committed)
- API keys validated on startup
- Minimum key length enforced
- `.env.example` for documentation only

### API Key Management
- Google AI API key required
- Validated at initialization
- Minimum length: 20 characters
- Stored securely in environment

## Database Security

### SQLAlchemy ORM
- Parameterized queries prevent SQL injection
- No raw SQL execution
- Input sanitization before queries

### Connection Security
- Connection pooling configured
- Timeout settings prevent hanging
- Proper session management

## Logging Security

### What We Log
- Authentication attempts (success/failure)
- API requests (endpoint, client IP)
- Errors and exceptions
- File uploads (filename, size)

### What We DON'T Log
- API keys or secrets
- Full file contents
- Personal identifiable information (PII)
- Password or sensitive data

### Log Management
- Rotating file handlers (10MB max)
- 5 backup files retained
- Logs stored in `logs/` directory
- Proper file permissions recommended

## Recommendations for Production

### 1. HTTPS Only
```python
# Force HTTPS in production
if config.environment == "production":
    app.add_middleware(HTTPSRedirectMiddleware)
```

### 2. Enhanced Authentication
- Implement JWT tokens
- Add refresh token mechanism
- Multi-factor authentication option
- Password hashing (if adding user accounts)

### 3. Database Security
- Use PostgreSQL instead of SQLite
- Enable SSL for database connections
- Regular backups
- Implement database migrations (Alembic)

### 4. Rate Limiting Enhancement
- Use Redis for distributed rate limiting
- Different limits per endpoint
- Whitelist trusted IPs
- Implement exponential backoff

### 5. File Upload Security
- Virus scanning integration
- Content-type validation
- Temporary file cleanup
- Sandboxed processing

### 6. Monitoring
- Set up security monitoring
- Alert on suspicious activity
- Track failed authentication attempts
- Monitor rate limit violations

### 7. API Security
- Implement API versioning
- Add request signing
- CORS configuration for production
- API documentation with security notes

## Security Checklist

- [x] Input validation on all endpoints
- [x] Rate limiting implemented
- [x] Error messages don't leak sensitive data
- [x] Logging configured properly
- [x] API key validation
- [x] File upload restrictions
- [x] SQL injection prevention (ORM)
- [x] Environment-based configuration
- [ ] HTTPS enforcement (production)
- [ ] Security headers (production)
- [ ] Database encryption (production)
- [ ] Regular security audits
- [ ] Dependency vulnerability scanning
- [ ] Penetration testing

## Reporting Security Issues

If you discover a security vulnerability:
1. Do NOT open a public issue
2. Email security concerns privately
3. Include detailed description
4. Provide steps to reproduce
5. Allow time for fix before disclosure

## Security Updates

- Review dependencies regularly
- Update to latest stable versions
- Monitor security advisories
- Test updates in staging first

## Compliance Notes

### Data Privacy
- No PII stored without consent
- Data retention policies configurable
- User data deletion on request
- Audit trail maintained

### GDPR Considerations
- Right to access data
- Right to deletion
- Data portability
- Consent management

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
