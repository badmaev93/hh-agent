## 2024-11-06 - Path Traversal in Screenshot Debug
**Vulnerability:** A path traversal vulnerability existed in `scripts/search_vacancies.py` where a user-provided search `query` was used to construct the filename for a debug screenshot (`debug_search_{query}.png`) with insufficient sanitization (only spaces were replaced with underscores). A malicious query like `../../../etc/passwd` could lead to writing the screenshot outside the intended `data/` directory.
**Learning:** Even internal tool scripts that dump debug outputs using user-provided strings (like a search query) are susceptible to path traversal. String operations like `replace(' ', '_')` are not enough to prevent directory climbing attacks (`../`).
**Prevention:** Use regular expressions to enforce a strict character allowlist (e.g., alphanumeric and dash `[^\w\-]`) on any user-provided string before incorporating it into a file path.
## 2024-11-06 - Prevent Playwright SSRF / Arbitrary Local File Access
**Vulnerability:** URLs passed to `page.goto()` were not validated. If an attacker controlled these URLs, they could trigger arbitrary local file access (via `file://` scheme) or Server-Side Request Forgery (SSRF) vulnerabilities.
**Learning:** Browser automation tools like Playwright can act as powerful vectors for SSRF and local file inclusion if navigation URLs are not strictly controlled, since they inherently trust standard browser schemes.
**Prevention:** Implement strict allowlisting of URL schemes (e.g. `http://`, `https://`) before passing any untrusted URL to navigation functions.
