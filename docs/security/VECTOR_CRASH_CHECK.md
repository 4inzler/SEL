## Vector Store Crash - Emergency Diagnostic

## 🔍 Step 1: Check Your Logs for Crash Evidence

Look for these in your FULL log file:

```bash
# Search for vector/memory errors
findstr /i "error memory" sel_bot.log
findstr /i "error him" sel_bot.log
findstr /i "corrupt" sel_bot.log
findstr /i "failed write" sel_bot.log
findstr /i "exception memory" sel_bot.log
```

**Look for:**
- `[sel_bot.memory] ERROR`
- `[sel_bot.memory_manager] ERROR`
- `Database locked`
- `Corruption detected`
- `Failed to write`
- `Cannot access`

---

## 🧪 Step 2: Run Diagnostic Tool

```bash
cd C:\Users\Public
python vector_store_diagnostics.py
```

**When prompted, enter:**
```
C:\Users\Administrator\Documents\SEL-main\project_echo\data\him_store
```

**This will check:**
- ✅ Database file exists
- ✅ Database is readable
- ✅ Database is NOT corrupted
- ⚠️ Contains HTML/JavaScript (from pentest)
- ✅ Can write to database
- ✅ Size is normal

---

## 🎯 Step 3: Manual Check

### Check if HIM store exists:
```bash
dir C:\Users\Administrator\Documents\SEL-main\project_echo\data\him_store
```

**Expected:**
```
Directory of C:\...\him_store

2025-12-28  09:05    <DIR>          .
2025-12-28  09:05    <DIR>          ..
2025-12-28  09:05        123,456    chroma.sqlite3
2025-12-28  09:05         12,345    index.bin
...
```

**If you see:**
- ❌ "File Not Found" → Store deleted/crashed
- ❌ "Access Denied" → Permission issue
- ❌ 0 byte files → Corruption

---

## 💥 Common Crash Causes from HTML/JS Injection

### 1. Embedding Failure
```
HTML: <!DOCTYPE html><script>...</script>
  ↓
Embedding model tries to tokenize
  ↓
Encounters malformed HTML
  ↓
💥 Crash: "Cannot tokenize"
```

### 2. Database Corruption
```
HTML with special chars: <>&"'
  ↓
SQLite tries to store
  ↓
Special chars break SQL query
  ↓
💥 Crash: "SQL syntax error"
```

### 3. Size Overflow
```
Large HTML document (100KB+)
  ↓
Vector store tries to embed
  ↓
Exceeds size limit
  ↓
💥 Crash: "Document too large"
```

### 4. Encoding Error
```
HTML entities: &lt; &gt; &amp;
  ↓
Vector store tries to decode
  ↓
Encoding mismatch
  ↓
💥 Crash: "UnicodeDecodeError"
```

---

## 🔍 Look for These Specific Errors

### ChromaDB Crash:
```
chromadb.errors.ChromaError: ...
Failed to add documents
Database is locked
```

### FAISS Crash:
```
RuntimeError: Error in faiss::...
IndexFlatL2::add() failed
Invalid dimension
```

### SQLite Crash:
```
sqlite3.DatabaseError: database disk image is malformed
sqlite3.OperationalError: database is locked
```

### Embedding Crash:
```
OpenAIError: Invalid input
RuntimeError: Embedding failed
TokenizationError: Cannot tokenize
```

---

## 🩹 Quick Fixes

### Fix 1: Restart with Clean DB
```bash
# Backup current DB
cd C:\Users\Administrator\Documents\SEL-main\project_echo\data
copy him_store him_store_backup_2025-12-28

# Delete corrupted DB (if confirmed corrupted)
# SEL will recreate on restart
```

### Fix 2: Remove HTML from DB (if accessible)
```python
# If DB is readable but contains HTML:
from vector_store_diagnostics import VectorStoreDiagnostics

diag = VectorStoreDiagnostics("path/to/him_store")
report = diag.check_for_malicious_content()

# If HTML found, you'll need to clean it manually or rebuild
```

### Fix 3: Add Input Validation (Prevent Future)
```python
# In discord_client.py, BEFORE storing in memory:

def is_safe_for_storage(content: str) -> bool:
    """Check if content is safe for vector storage"""
    # Block HTML
    if '<' in content and '>' in content:
        if any(tag in content.lower() for tag in ['<script', '<html', '<!doctype']):
            return False

    # Block very long messages
    if len(content) > 10000:
        return False

    return True

# Use it:
if is_safe_for_storage(message.content):
    await self.store_memory(message.content)
else:
    logger.warning(f"Blocked unsafe content from memory storage")
```

---

## 📊 Expected Diagnostic Output

### If Vector Store is OK:
```
===== VECTOR STORE DIAGNOSTICS =====
✅ HIM store found
✅ Database readable (5 tables)
✅ Can write to vector store
✅ Size normal: 12.5 MB
⚠️  Found HTML in: snapshot_123.json
⚠️  Found <script> in: snapshot_124.json

SUMMARY:
⚠️  WARNINGS (2):
  • Found HTML/JS in 2 files

✅ Database is functional but contains malicious content
```

### If Vector Store Crashed:
```
===== VECTOR STORE DIAGNOSTICS =====
✅ HIM store found
❌ Database corrupted: database disk image is malformed
❌ Cannot write to vector store
❌ No database files found

SUMMARY:
❌ ERRORS (3):
  • Database corrupted
  • Cannot write
  • No database files

❌ CRASH DETECTED - Database is corrupted!
```

---

## 🆘 If Crashed - Recovery Steps

### 1. Check Backups
```bash
# SEL might have auto-backups
dir C:\Users\Administrator\Documents\SEL-main\project_echo\data\*backup*
dir C:\Users\Administrator\Documents\SEL-main\project_echo\data\*.bak
```

### 2. Try DB Recovery
```bash
# For SQLite corruption
sqlite3 him_store\chroma.sqlite3 ".recover" > recovered.sql
```

### 3. Rebuild from Snapshots
```bash
# If HIM has snapshots
# Check for snapshot files that aren't corrupted
dir him_store\snapshots\
```

### 4. Nuclear Option: Start Fresh
```bash
# Backup
move him_store him_store_corrupted_2025-12-28

# SEL will create new DB on restart
# You'll lose old memories but bot will work
```

---

## 🛡️ Prevention for Future

Add this to SEL BEFORE storing:

```python
from html_xss_protection import HTMLXSSDetector

# Before storing in vector DB:
if HTMLXSSDetector.is_html_message(content):
    logger.warning(f"Blocking HTML from vector storage: {content[:50]}...")
    content = HTMLXSSDetector.sanitize(content)
    # Store sanitized or don't store at all

await self.store_memory(content)
```

---

## 📞 Report Back

After running diagnostics, tell me:

1. **Does HIM store directory exist?** (Yes/No)
2. **Any database files found?** (Yes/No)
3. **Database readable?** (Yes/No)
4. **Contains HTML/JavaScript?** (Yes/No)
5. **Can write to database?** (Yes/No)
6. **Any error messages?** (Paste them)

**I'll help you recover based on results!**
