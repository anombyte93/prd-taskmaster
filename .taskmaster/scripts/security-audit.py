#!/usr/bin/env python3
"""
Auto-generate security audit checklist based on implemented features.
"""

import re
from pathlib import Path

def detect_security_concerns(codebase_path="."):
    """Scan code for security-relevant features."""
    concerns = []

    # Scan for authentication-related code
    for file_path in Path(codebase_path).rglob("*.{js,ts,py,go,java}"):
        try:
            content = file_path.read_text()

            # Check for password handling
            if re.search(r'password|passwd|pwd', content, re.I):
                concerns.append({
                    "category": "Authentication",
                    "item": "Password hashing",
                    "check": "Passwords hashed with bcrypt/argon2 (cost ≥ 10)",
                    "file": str(file_path)
                })

            # Check for OAuth
            if re.search(r'oauth|openid', content, re.I):
                concerns.append({
                    "category": "OAuth",
                    "item": "OAuth token security",
                    "check": "OAuth tokens encrypted at rest and in transit",
                    "file": str(file_path)
                })

            # Check for database queries
            if re.search(r'SELECT.*FROM|INSERT INTO|UPDATE.*SET', content, re.I):
                concerns.append({
                    "category": "Database",
                    "item": "SQL injection prevention",
                    "check": "All queries use parameterized statements (no string concatenation)",
                    "file": str(file_path)
                })

            # Check for user input handling
            if re.search(r'req\.body|request\.form|input\(', content):
                concerns.append({
                    "category": "Input Validation",
                    "item": "XSS prevention",
                    "check": "All user input sanitized before rendering",
                    "file": str(file_path)
                })
        except:
            pass  # Skip files that can't be read

    # Deduplicate
    unique_concerns = []
    seen = set()
    for c in concerns:
        key = (c["category"], c["item"])
        if key not in seen:
            unique_concerns.append(c)
            seen.add(key)

    return unique_concerns

def generate_security_checklist():
    """Generate comprehensive security audit checklist."""
    concerns = detect_security_concerns()

    checklist = """
🔒 SECURITY AUDIT CHECKLIST

Auto-generated based on your implementation.

"""

    # Group by category
    by_category = {}
    for c in concerns:
        cat = c["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(c)

    for category, items in sorted(by_category.items()):
        checklist += f"\n### {category}\n"
        for item in items:
            checklist += f"- [ ] {item['check']}\n"
            checklist += f"      File: {item['file']}\n"

    # Add standard checks
    checklist += """

### General Security
- [ ] HTTPS enforced in production
- [ ] CSRF protection enabled
- [ ] Rate limiting on sensitive endpoints
- [ ] Security headers set (CSP, X-Frame-Options, etc.)
- [ ] Dependencies audited (npm audit / pip-audit)
- [ ] Secrets not committed to git (.env in .gitignore)
- [ ] Error messages don't leak sensitive info
- [ ] Logging doesn't include passwords/tokens

### Compliance (if applicable)
- [ ] GDPR: User data deletion implemented
- [ ] SOC2: Audit logs for all auth events
- [ ] PCI-DSS: No credit card data stored

"""

    checklist += """
🧪 Automated Security Scans Available:

1. npm audit (Node.js dependencies)
2. pip-audit (Python dependencies)
3. OWASP ZAP (web application scan)
4. Snyk (vulnerability scanning)

Run automated scans?
  1. Yes, run npm audit + recommended scans
  2. Manual review only
  3. Skip for now

"""

    return checklist

if __name__ == "__main__":
    print(generate_security_checklist())
