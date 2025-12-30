"""
Vector Store Diagnostics for SEL Bot
Check if HTML/JS injection corrupted the vector database
"""

import os
import json
import sqlite3
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('vector_diagnostics')


class VectorStoreDiagnostics:
    """
    Diagnose vector store health and corruption
    """

    def __init__(self, him_store_path: str):
        """
        Args:
            him_store_path: Path to SEL's HIM store
                           (e.g., C:/Users/Administrator/Documents/SEL-main/project_echo/data/him_store)
        """
        self.him_store_path = Path(him_store_path)
        self.errors = []
        self.warnings = []

    def check_directory_exists(self) -> bool:
        """Check if HIM store directory exists"""
        if not self.him_store_path.exists():
            self.errors.append(f"HIM store not found at: {self.him_store_path}")
            return False

        logger.info(f"✅ HIM store found at: {self.him_store_path}")
        return True

    def check_database_files(self) -> dict:
        """Check for database files and their integrity"""
        results = {
            'db_file_exists': False,
            'db_readable': False,
            'db_corrupted': False,
            'db_size_mb': 0,
            'files_found': []
        }

        # Look for common vector DB files
        db_patterns = [
            '*.db',
            '*.sqlite',
            '*.sqlite3',
            'chroma.sqlite3',
            '*.index',
            'index.faiss',
            '*.bin'
        ]

        for pattern in db_patterns:
            found_files = list(self.him_store_path.glob(pattern))
            if found_files:
                results['files_found'].extend([str(f) for f in found_files])

        if results['files_found']:
            results['db_file_exists'] = True
            logger.info(f"✅ Found {len(results['files_found'])} database file(s)")

            # Check first database file
            db_file = Path(results['files_found'][0])
            results['db_size_mb'] = db_file.stat().st_size / (1024 * 1024)
            logger.info(f"   Database size: {results['db_size_mb']:.2f} MB")

            # Try to open if it's SQLite
            if db_file.suffix in ['.db', '.sqlite', '.sqlite3']:
                try:
                    conn = sqlite3.connect(str(db_file))
                    cursor = conn.cursor()

                    # Try a simple query
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                    tables = cursor.fetchall()

                    results['db_readable'] = True
                    logger.info(f"✅ Database readable ({len(tables)} tables)")

                    conn.close()
                except sqlite3.DatabaseError as e:
                    results['db_corrupted'] = True
                    self.errors.append(f"Database corrupted: {e}")
                    logger.error(f"❌ Database corrupted: {e}")
                except Exception as e:
                    self.warnings.append(f"Could not read database: {e}")
                    logger.warning(f"⚠️  Could not read database: {e}")
        else:
            self.errors.append("No database files found in HIM store")
            logger.error(f"❌ No database files found")

        return results

    def check_for_malicious_content(self) -> dict:
        """Check if vector store contains HTML/JS (from pentest)"""
        results = {
            'contains_html': False,
            'contains_javascript': False,
            'contains_scripts': False,
            'suspicious_count': 0,
            'examples': []
        }

        # Look for JSON files that might contain embeddings/memories
        json_files = list(self.him_store_path.glob('**/*.json'))

        for json_file in json_files[:10]:  # Check first 10 files
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                    # Check for HTML/JS
                    if '<!DOCTYPE' in content or '<html' in content:
                        results['contains_html'] = True
                        results['suspicious_count'] += 1
                        results['examples'].append(f"{json_file.name}: Contains HTML")
                        logger.warning(f"⚠️  Found HTML in: {json_file.name}")

                    if '<script' in content:
                        results['contains_javascript'] = True
                        results['contains_scripts'] = True
                        results['suspicious_count'] += 1
                        results['examples'].append(f"{json_file.name}: Contains <script>")
                        logger.warning(f"⚠️  Found <script> in: {json_file.name}")

                    if 'javascript:' in content:
                        results['contains_javascript'] = True
                        results['suspicious_count'] += 1
                        results['examples'].append(f"{json_file.name}: Contains javascript:")
                        logger.warning(f"⚠️  Found javascript: protocol in: {json_file.name}")

            except Exception as e:
                self.warnings.append(f"Could not read {json_file.name}: {e}")

        if results['suspicious_count'] > 0:
            logger.error(f"❌ Found {results['suspicious_count']} files with HTML/JS!")
        else:
            logger.info("✅ No obvious HTML/JS in JSON files")

        return results

    def check_recent_writes(self) -> dict:
        """Check if vector store can be written to"""
        results = {
            'can_write': False,
            'recent_files': [],
            'last_write_time': None
        }

        # Find recently modified files
        all_files = list(self.him_store_path.glob('**/*'))

        if all_files:
            # Sort by modification time
            all_files.sort(key=lambda f: f.stat().st_mtime if f.is_file() else 0, reverse=True)

            recent = all_files[:5]
            for f in recent:
                if f.is_file():
                    mtime = f.stat().st_mtime
                    import datetime
                    dt = datetime.datetime.fromtimestamp(mtime)
                    results['recent_files'].append({
                        'name': f.name,
                        'modified': dt.isoformat(),
                        'size_kb': f.stat().st_size / 1024
                    })

            if recent:
                results['last_write_time'] = datetime.datetime.fromtimestamp(
                    recent[0].stat().st_mtime
                ).isoformat()
                results['can_write'] = True
                logger.info(f"✅ Last write: {results['last_write_time']}")

        # Try to write a test file
        test_file = self.him_store_path / '.diagnostic_test'
        try:
            test_file.write_text('test')
            test_file.unlink()
            results['can_write'] = True
            logger.info("✅ Can write to vector store")
        except Exception as e:
            results['can_write'] = False
            self.errors.append(f"Cannot write to vector store: {e}")
            logger.error(f"❌ Cannot write: {e}")

        return results

    def check_size_anomalies(self) -> dict:
        """Check for unusual size growth (could indicate corruption)"""
        results = {
            'total_size_mb': 0,
            'file_count': 0,
            'large_files': [],
            'size_anomaly': False
        }

        all_files = [f for f in self.him_store_path.glob('**/*') if f.is_file()]
        results['file_count'] = len(all_files)

        total_size = sum(f.stat().st_size for f in all_files)
        results['total_size_mb'] = total_size / (1024 * 1024)

        # Find large files
        for f in all_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            if size_mb > 10:  # Larger than 10 MB
                results['large_files'].append({
                    'name': f.name,
                    'size_mb': size_mb
                })

        if results['total_size_mb'] > 500:  # Over 500 MB
            results['size_anomaly'] = True
            self.warnings.append(f"Vector store is very large: {results['total_size_mb']:.2f} MB")
            logger.warning(f"⚠️  Large vector store: {results['total_size_mb']:.2f} MB")
        else:
            logger.info(f"✅ Size normal: {results['total_size_mb']:.2f} MB")

        return results

    def run_full_diagnostic(self) -> dict:
        """Run all diagnostics"""
        print("="*80)
        print("VECTOR STORE DIAGNOSTICS")
        print("="*80)
        print(f"\nChecking: {self.him_store_path}\n")

        report = {}

        # 1. Check directory
        if not self.check_directory_exists():
            print("\n❌ CRITICAL: Vector store directory not found!")
            return report

        # 2. Check database files
        print("\n--- Database Files ---")
        report['database'] = self.check_database_files()

        # 3. Check for malicious content
        print("\n--- Malicious Content Check ---")
        report['malicious'] = self.check_for_malicious_content()

        # 4. Check recent writes
        print("\n--- Write Check ---")
        report['writes'] = self.check_recent_writes()

        # 5. Check size
        print("\n--- Size Check ---")
        report['size'] = self.check_size_anomalies()

        # Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for err in self.errors:
                print(f"  • {err}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warn in self.warnings:
                print(f"  • {warn}")

        if not self.errors and not self.warnings:
            print("\n✅ No major issues detected")

        # Crash indicators
        print("\n--- CRASH INDICATORS ---")
        crash_indicators = []

        if report.get('database', {}).get('db_corrupted'):
            crash_indicators.append("Database is corrupted")

        if not report.get('writes', {}).get('can_write'):
            crash_indicators.append("Cannot write to vector store")

        if report.get('malicious', {}).get('contains_html'):
            crash_indicators.append("Contains HTML (may have caused corruption)")

        if report.get('malicious', {}).get('contains_scripts'):
            crash_indicators.append("Contains JavaScript (may have caused corruption)")

        if crash_indicators:
            print("❌ POSSIBLE CRASH CAUSES:")
            for indicator in crash_indicators:
                print(f"  • {indicator}")
        else:
            print("✅ No obvious crash indicators")

        return report


def main():
    """Run diagnostics on SEL's vector store"""

    # Update this path to your SEL HIM store
    him_store_path = input(
        "Enter path to HIM store\n"
        "(e.g., C:\\Users\\Administrator\\Documents\\SEL-main\\project_echo\\data\\him_store):\n"
    ).strip()

    if not him_store_path:
        him_store_path = r"C:\Users\Administrator\Documents\SEL-main\project_echo\data\him_store"
        print(f"Using default: {him_store_path}")

    diagnostics = VectorStoreDiagnostics(him_store_path)
    report = diagnostics.run_full_diagnostic()

    # Save report
    import json
    report_file = Path("vector_store_diagnostic_report.json")
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n📄 Report saved to: {report_file.absolute()}")


if __name__ == "__main__":
    main()
