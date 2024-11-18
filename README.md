# JADX Context Generator

A Python script that integrates with JADX to analyze Java/Android code and generate context for Large Language Models (LLMs). This tool is particularly useful for analyzing decompiled Android applications and generating contextual information while adhering to token limits.

## Features

- **JADX Integration**: Seamlessly works with JADX for decompiling Android APKs
- **Package Filtering**: Support for whitelist/blacklist patterns with wildcards
- **Token Management**: Precise token counting and optimization for LLM context windows
- **Class Hierarchy Analysis**: Traces class relationships and usages
- **Performance Optimizations**: 
  - Batch processing for large codebases
  - SQLite-based indexing
  - Multi-threaded processing
  - Memory-efficient file handling

## Prerequisites

```bash
pip install tqdm sqlite3
```

You'll also need JADX installed on your system. You can get it from [https://github.com/skylot/jadx](https://github.com/skylot/jadx)

## Usage

Basic usage:
```bash
python context-builder.py \
    --jadx-path "/path/to/jadx" \
    --apk-path "/path/to/your.apk" \
    --target-class "com.example.TargetClass" \
    --whitelist "com.example.*" \
    --batch-size 4000
```

Options:
- `--jadx-path`: Path to JADX executable
- `--apk-path`: Path to target APK file
- `--target-class`: Target class or package pattern to analyze
- `--whitelist`: Package patterns to include (supports wildcards)
- `--blacklist`: Package patterns to exclude (supports wildcards)
- `--batch-size`: Number of files to process in each batch (default: 1000)
- `--output`: Output file path (optional)
- `--verbose`: Enable verbose logging

## Examples

1. Analyze a specific class:
```bash
python context-builder.py \
    --jadx-path "/path/to/jadx" \
    --apk-path "app.apk" \
    --target-class "com.example.MainActivity"
```

2. Analyze a package with whitelist:
```bash
python context-builder.py \
    --jadx-path "/path/to/jadx" \
    --apk-path "app.apk" \
    --target-class "com.example.feature.*" \
    --whitelist "com.example.*" "com.example.utils.*"
```

3. Exclude certain packages:
```bash
python context-builder.py \
    --jadx-path "/path/to/jadx" \
    --apk-path "app.apk" \
    --target-class "com.example.MyClass" \
    --whitelist "com.example.*" \
    --blacklist "com.example.internal.*"
```

## Token Management

The script manages tokens to fit within LLM context windows:
- Default maximum tokens: 100,000
- Optimizes code by removing unnecessary whitespace and comments
- Preserves code functionality while reducing token count
- Provides accurate token counting for code

## Output

The script generates context that includes:
- Target class/package code
- Related class hierarchies
- Usage relationships
- Referenced classes
- Dependencies within whitelist patterns

## Large-Scale Usage

For large applications:
- Use appropriate batch size (e.g., 4000-8000)
- Enable verbose logging to monitor progress
- Consider using blacklist to exclude unnecessary packages
- Monitor memory usage and adjust batch size accordingly

## Error Handling

The script handles common errors:
- Invalid JADX paths
- Decompilation failures
- Memory constraints
- Invalid package patterns
- Missing classes/files

## Limitations

- Maximum context size of 100k tokens
- Requires JADX for decompilation
- Memory usage scales with codebase size
- Some obfuscated code may not decompile properly

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the LICENSE file for details.
