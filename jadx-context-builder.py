

import os

import re

import subprocess

import argparse

import logging

from typing import List, Set, Dict

from pathlib import Path

from concurrent.futures import ThreadPoolExecutor

from collections import defaultdict

import json

import sqlite3

from tqdm import tqdm

import fnmatch

import shutil



class JadxContextGenerator:

    def __init__(self, jadx_path: str, target_apk: str, output_file: str = None, verbose: bool = False):

        self.jadx_path = jadx_path

        self.target_apk = target_apk

        self.output_file = output_file

        self.output_dir = "decompiled_output"

        self.MAX_TOKENS = 100000

        self.index_db = "jadx_index.db"

        

        # Setup logging

        log_level = logging.DEBUG if verbose else logging.INFO

        logging.basicConfig(level=log_level, 

                          format='%(asctime)s - %(levelname)s - %(message)s')

        self.logger = logging.getLogger(__name__)

        

        # Initialize SQLite connection

        self.conn = None

        self.setup_index_db()



    def setup_index_db(self):

        """Initialize SQLite database for indexing"""

        try:

            # Remove existing database if it exists

            if os.path.exists(self.index_db):

                os.remove(self.index_db)

                

            self.conn = sqlite3.connect(self.index_db)

            cursor = self.conn.cursor()

            

            # Create tables

            cursor.execute('''

                CREATE TABLE IF NOT EXISTS class_index (

                    class_name TEXT PRIMARY KEY,

                    file_path TEXT,

                    package TEXT

                )

            ''')

            

            cursor.execute('''

                CREATE TABLE IF NOT EXISTS class_references (

                    source_class TEXT,

                    target_class TEXT,

                    reference_type TEXT,

                    UNIQUE(source_class, target_class, reference_type)

                )

            ''')

            

            # Create indexes

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_package ON class_index(package)')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_references ON class_references(source_class, target_class)')

            

            self.conn.commit()

            self.logger.debug("Database initialized successfully")

        except sqlite3.Error as e:

            self.logger.error(f"Database initialization error: {str(e)}")

            raise



    def setup_jadx(self, jadx_args: List[str] = None) -> bool:

        """Initialize jadx with correct options."""

        try:

            # Clean up previous output

            if os.path.exists(self.output_dir):

                shutil.rmtree(self.output_dir)

            os.makedirs(self.output_dir, exist_ok=True)



            # Base command with valid options only

            cmd = [

                self.jadx_path,

                self.target_apk,

                "-d", self.output_dir,

                "--threads-count", str(os.cpu_count()),

                "--deobf",         # Enable deobfuscation

                "--show-bad-code", # Show code that failed to decompile

                "--no-res",        # Skip resources to speed up

                "--escape-unicode" # Escape unicode characters

            ]

            

            self.logger.info(f"Running jadx command: {' '.join(cmd)}")

            result = subprocess.run(cmd, capture_output=True, text=True)

            

            if result.stdout:

                self.logger.debug(f"jadx stdout:\n{result.stdout}")

            if result.stderr:

                self.logger.error(f"jadx stderr:\n{result.stderr}")



            # Check if decompilation succeeded

            java_files = list(Path(self.output_dir).rglob("*.java"))

            if not java_files:

                self.logger.error("No Java files found after decompilation!")

                # List directory contents for debugging

                self.logger.debug("Output directory contents:")

                for root, dirs, files in os.walk(self.output_dir):

                    self.logger.debug(f"Directory: {root}")

                    for d in dirs:

                        self.logger.debug(f"  Subdirectory: {d}")

                    for f in files:

                        self.logger.debug(f"  File: {f}")

                return False



            self.logger.info(f"Found {len(java_files)} Java files")

            

            # Sample the first few files to verify content

            for file in java_files[:5]:

                self.logger.debug(f"Sample file: {file}")

                try:

                    with open(file, 'r', encoding='utf-8') as f:

                        self.logger.debug(f"First few lines: {f.readline()[:100]}")

                except Exception as e:

                    self.logger.warning(f"Error reading {file}: {str(e)}")



            self._build_class_index()

            return True

            

        except Exception as e:

            self.logger.error(f"Error setting up jadx: {str(e)}")

            import traceback

            self.logger.error(traceback.format_exc())

            return False



    def _build_class_index(self):

        """Build index of all decompiled classes with enhanced path handling."""

        self.logger.info("Building class index...")

        

        # Search in multiple possible locations

        search_paths = [

            os.path.join(self.output_dir, 'sources'),

            os.path.join(self.output_dir, 'src', 'main', 'java'),

            self.output_dir,

        ]

        

        cursor = self.conn.cursor()

        total_files = 0

        

        for search_path in search_paths:

            if not os.path.exists(search_path):

                self.logger.debug(f"Path does not exist: {search_path}")

                continue

                

            self.logger.info(f"Searching in: {search_path}")

            java_files = list(Path(search_path).rglob("*.java"))

            

            for file_path in tqdm(java_files, desc=f"Indexing classes in {search_path}"):

                try:

                    relative_path = file_path.relative_to(search_path)

                    class_name = str(relative_path.with_suffix('')).replace(os.sep, '.')

                    package = '.'.join(class_name.split('.')[:-1])

                    

                    cursor.execute(

                        'INSERT OR REPLACE INTO class_index (class_name, file_path, package) VALUES (?, ?, ?)',

                        (class_name, str(file_path), package)

                    )

                    total_files += 1

                except Exception as e:

                    self.logger.warning(f"Error indexing {file_path}: {str(e)}")

        

        self.conn.commit()

        self.logger.info(f"Indexed {total_files} classes")



    def find_class_file(self, class_name: str) -> str:

        """Find the .java file for a given class name with enhanced debugging."""

        self.logger.debug(f"Looking for class file: {class_name}")

        

        # Try database first

        if self.conn:

            cursor = self.conn.cursor()

            cursor.execute('SELECT file_path FROM class_index WHERE class_name = ?', (class_name,))

            result = cursor.fetchone()

            if result:

                self.logger.debug(f"Found in database: {result[0]}")

                return result[0]

        

        # List all possible paths to search

        search_paths = [

            os.path.join(self.output_dir, 'sources'),

            os.path.join(self.output_dir, 'src', 'main', 'java'),

            os.path.join(self.output_dir),

        ]

        

        # Log all Java files found

        self.logger.debug("Searching for Java files in:")

        for search_path in search_paths:

            if os.path.exists(search_path):

                self.logger.debug(f"Searching in: {search_path}")

                java_files = list(Path(search_path).rglob("*.java"))

                self.logger.debug(f"Found {len(java_files)} Java files")

                for java_file in java_files:

                    self.logger.debug(f"Found file: {java_file}")

                    # Convert path to class name

                    relative_path = java_file.relative_to(search_path)

                    potential_class_name = str(relative_path.with_suffix('')).replace(os.sep, '.')

                    if class_name.lower() in potential_class_name.lower():  # Case-insensitive comparison

                        self.logger.debug(f"Matched class name: {potential_class_name}")

                        return str(java_file)

        

        self.logger.warning(f"Class file not found for {class_name} in any search path")

        return None



    def get_class_hierarchy(self, class_name: str) -> Dict:

        """Get class hierarchy information."""

        hierarchy = {

            'superclasses': [],

            'interfaces': [],

            'inner_classes': [],

            'referenced_classes': set(),

            'using_classes': set()

        }

        

        class_file = self.find_class_file(class_name)

        if not class_file:

            self.logger.warning(f"Class file not found for {class_name}")

            return hierarchy

            

        try:

            with open(class_file, 'r', encoding='utf-8') as f:

                content = f.read()

                

            # Extract superclass

            super_match = re.search(r'extends\s+([A-Za-z0-9_.]+)', content)

            if super_match:

                hierarchy['superclasses'].append(super_match.group(1))

                

            # Extract interfaces

            interface_match = re.search(r'implements\s+([A-Za-z0-9_.,\s]+)', content)

            if interface_match:

                interfaces = [i.strip() for i in interface_match.group(1).split(',')]

                hierarchy['interfaces'].extend(interfaces)

                

            # Find referenced classes

            class_refs = re.findall(r'([A-Za-z0-9_]+\.[A-Za-z0-9_.]+)', content)

            hierarchy['referenced_classes'].update(class_refs)

            

            # Find using classes

            hierarchy['using_classes'] = self.trace_usage(class_name)

            

        except Exception as e:

            self.logger.error(f"Error getting hierarchy for {class_name}: {str(e)}")

            

        return hierarchy



    def trace_usage(self, class_name: str) -> Set[str]:

        """Trace all usages of the specified class."""

        usage_classes = set()

        class_simple_name = class_name.split('.')[-1]

        

        if not self.conn:

            return usage_classes



        cursor = self.conn.cursor()

        cursor.execute('SELECT file_path FROM class_index')

        files = cursor.fetchall()

        

        for file_path, in tqdm(files, desc=f"Tracing usage of {class_name}"):

            try:

                with open(file_path, 'r', encoding='utf-8') as f:

                    content = f.read()

                    

                if class_name in content or class_simple_name in content:

                    relative_path = str(Path(file_path).relative_to(self.output_dir).with_suffix('')).replace(os.sep, '.')

                    usage_classes.add(relative_path)

                    

            except Exception as e:

                self.logger.warning(f"Error processing {file_path}: {str(e)}")

                

        return usage_classes



    def matches_package_filter(self, package: str, whitelist: List[str], blacklist: List[str]) -> bool:

        """Check if package matches whitelist/blacklist rules."""

        # First check blacklist

        for black in blacklist:

            if fnmatch.fnmatch(package, black):

                return False

        

        # Then check whitelist

        for white in whitelist:

            if fnmatch.fnmatch(package, white):

                return True

        

        return len(whitelist) == 0  # If no whitelist, accept all non-blacklisted



    def get_class_content(self, class_name: str) -> str:

        """Get the content of a class file."""

        class_file = self.find_class_file(class_name)

        if not class_file:

            self.logger.warning(f"Class file not found for {class_name}")

            return ""

            

        try:

            with open(class_file, 'r', encoding='utf-8') as f:

                return f.read()

        except Exception as e:

            self.logger.warning(f"Error reading {class_file}: {str(e)}")

            return ""



    def optimize_code_tokens(self, code: str) -> str:

        """Optimize code to reduce token count while preserving functionality."""

        # Remove unnecessary whitespace

        code = re.sub(r'\s+', ' ', code)

        code = re.sub(r'\s*{\s*', '{', code)

        code = re.sub(r'\s*}\s*', '}', code)

        

        # Remove comments

        code = re.sub(r'//.*?\n', '\n', code)

        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

        

        # Remove empty lines

        code = re.sub(r'\n\s*\n', '\n', code)

        

        return code.strip()



    def calculate_tokens(self, text: str) -> int:

        """Calculate approximate token count for Mistral."""

        words = re.findall(r'\w+|[^\w\s]', text)

        special_tokens = len(re.findall(r'[{}\[\]()<>]', text))

        whitespace = len(re.findall(r'\s+', text))

        return int((len(words) + special_tokens + whitespace) * 1.2)



    def generate_context(self, target_class: str, whitelist: List[str] = None, blacklist: List[str] = None) -> str:

        """Generate context for the target class with package filtering."""

        if whitelist is None:

            whitelist = []

        if blacklist is None:

            blacklist = []

            

        self.logger.info(f"Generating context for {target_class}")

        context_parts = []

        processed_classes = set()

        classes_to_process = [target_class]

        total_tokens = 0

        

        while classes_to_process and total_tokens < self.MAX_TOKENS:

            current_class = classes_to_process.pop(0)

            if current_class in processed_classes:

                continue

                

            # Check package filters

            if not self.matches_package_filter(current_class, whitelist, blacklist):

                continue

                

            class_content = self.get_class_content(current_class)

            if not class_content:

                continue

                

            # Optimize code to reduce tokens

            optimized_content = self.optimize_code_tokens(class_content)

            tokens_needed = self.calculate_tokens(optimized_content)

            

            if total_tokens + tokens_needed <= self.MAX_TOKENS:

                context_parts.append(optimized_content)

                total_tokens += tokens_needed

                

                # Add related classes to processing queue

                hierarchy = self.get_class_hierarchy(current_class)

                classes_to_process.extend(hierarchy['superclasses'])

                classes_to_process.extend(hierarchy['interfaces'])

                classes_to_process.extend(hierarchy['referenced_classes'])

                

            processed_classes.add(current_class)

            

        self.logger.info(f"Generated context with {total_tokens} tokens from {len(processed_classes)} classes")

        return "\n\n".join(context_parts)



    def cleanup(self):

        """Cleanup temporary files and database."""

        if self.conn:

            self.conn.close()

        if os.path.exists(self.index_db):

            os.remove(self.index_db)

        if os.path.exists(self.output_dir):

            shutil.rmtree(self.output_dir)



def main():

    parser = argparse.ArgumentParser(description='Generate context from Java/Android code using jadx')

    parser.add_argument('--jadx-path', required=True, help='Path to jadx executable')

    parser.add_argument('--apk-path', required=True, help='Path to target APK file')

    parser.add_argument('--target-class', required=True, help='Target class or package pattern')

    parser.add_argument('--whitelist', nargs='*', default=[], 

                      help='Whitelist package patterns (e.g., "com.example.*")')

    parser.add_argument('--blacklist', nargs='*', default=[],

                      help='Blacklist package patterns (e.g., "com.example.internal.*")')

    parser.add_argument('--output', help='Output file path')

    parser.add_argument('--batch-size', type=int, default=1000,

                      help='Batch size for processing large files')

    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')

    

    args = parser.parse_args()

    

    try:

        generator = JadxContextGenerator(

            args.jadx_path,

            args.apk_path,

            args.output,

            args.verbose

        )

        

        if not generator.setup_jadx(None):

            return

            

        context = generator.generate_context(

            target_class=args.target_class,

            whitelist=args.whitelist,

            blacklist=args.blacklist

        )

        

        if args.output:

            with open(args.output, 'w', encoding='utf-8') as f:

                f.write(context)

            print(f"Context written to {args.output}")

        else:

            print(context)

        

        print(f"Generated context with {generator.calculate_tokens(context)} tokens")

    except Exception as e:

        logging.error(f"Error: {str(e)}")

        raise  # Re-raise the exception for debugging

    finally:

        if 'generator' in locals():

            generator.cleanup()



if __name__ == "__main__":

    main()

