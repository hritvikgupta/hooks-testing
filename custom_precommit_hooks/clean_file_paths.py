import re
import os
import argparse
import subprocess
import glob
import logging
import json

def is_binary_file(filepath):
    try:
        with open(filepath, 'rb') as file:
            for block in iter(lambda: file.read(1024), b''):
                if b'\0' in block:
                    return True
        return False
    except Exception as e:
        logging.error(f"Error checking if file is binary: {e}")
        return False  # Assume non-binary on error

def clean_file(filepath, patterns):
    # Skip .json and .yaml files
    if filepath.endswith(('.json', '.yaml', '.yml')):
        logging.info(f"Skipping file: {filepath}")
        return False

    if is_binary_file(filepath):
        logging.info(f"Skipping binary file: {filepath}")
        return False
    
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()

        logging.info(f"Original content of {filepath}:\n{content[:200]}")  # Show first 200 characters for brevity

        cleaned_content = content
        for pattern, options in patterns.items():
            replacement = options.get("replacement")
            inplace = options.get("inplace", False)
            case_sensitive = options.get("case_sensitive", True)

            # Adjust regex pattern for case sensitivity
            flags = 0 if case_sensitive else re.IGNORECASE

            if inplace:
                # Pattern for matching and replacing specific paths
                flexible_pattern = re.compile(
                    rf'\b{re.escape(pattern)}\b',
                    flags
                )
                def replace_path(match):
                    # Replace the entire path with the replacement directory and the original filename
                    filename = os.path.basename(match.group(0))
                    new_path = os.path.join(replacement, filename)
                    logging.info(f"Replacing path: {match.group(0)} with {new_path}")
                    return new_path

                cleaned_content = flexible_pattern.sub(replace_path, cleaned_content)
            else:
                # Pattern for matching variable assignment with word boundaries to avoid partial matches
                assignment_pattern = re.compile(
                    rf'\b(?P<key>{re.escape(pattern)})\b(\s*=\s*)(?P<value>[^\n]*)',
                    flags
                )
                def replace_value(match):
                    key = match.group('key')
                    logging.info(f"Replacing value for key '{key}' with {replacement}")
                    return f"{key} = {replacement}"

                cleaned_content = assignment_pattern.sub(replace_value, cleaned_content)

        if content != cleaned_content:
            logging.info(f"Modified content of {filepath}:\n{cleaned_content[:200]}")  # Show first 200 characters for brevity
            with open(filepath, 'w', encoding='utf-8') as file:
                file.write(cleaned_content)
            logging.info(f"File modified: {filepath}")
            return True
        else:
            logging.info(f"No changes needed for file: {filepath}")
            return False

    except Exception as e:
        logging.error(f"Error cleaning file {filepath}: {e}")
        return False


def clean_files(patterns, include_dirs=None, enforce_all=False):
    if enforce_all:
        all_files = []
        for root, _, files in os.walk('.'):
            for file in files:
                filepath = os.path.join(root, file)
                if include_dirs:
                    if any(os.path.abspath(filepath).startswith(os.path.abspath(include_dir)) for include_dir in include_dirs):
                        all_files.append(filepath)
                else:
                    all_files.append(filepath)
        relevant_files = all_files
    else:
        relevant_files = subprocess.check_output(['git', 'diff', '--cached', '--name-only']).decode().splitlines()

    modified_files = []
    for filepath in relevant_files:
        if os.path.exists(filepath):
            if clean_file(filepath, patterns):
                modified_files.append(filepath)
    
    if modified_files:
        subprocess.check_call(["git", "add"] + modified_files)
        logging.info(f"Re-staged modified files.")
        logging.info("Please review the changes before committing.")
        return 1  # Return non-zero to abort the commit
    return 0

def main():
    logging.info("\n### Cleaning Files Hook ###")
    parser = argparse.ArgumentParser()
    parser.add_argument('--json-config', help='Path to JSON config file', type=str)
    parser.add_argument('--enforce-all', action='store_true', help='Enforce cleaning all relevant files, not just staged files')
    args, unknown = parser.parse_known_args()

    if args.json_config:
        with open(args.json_config, 'r') as f:
            config = json.load(f)
            patterns = config['patterns']
            include_dirs = config['directories']
            logging.info(f"Loaded JSON config: {config}")
    else:
        logging.error("JSON config file is required.")
        return 1

    if include_dirs:
        expanded_dirs = []
        for dir_pattern in include_dirs:
            matching_dirs = glob.glob(dir_pattern)
            expanded_dirs.extend(matching_dirs)
        include_dirs = expanded_dirs

    return clean_files(patterns, include_dirs, args.enforce_all)

if __name__ == '__main__':
    logging.basicConfig(filename='pre_commit.log', level=logging.INFO)
    raise SystemExit(main())
