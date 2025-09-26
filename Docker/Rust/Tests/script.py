import os


def find_rust_tests(directory):
    rust_tests = []

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".rs"):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                    in_test = False
                    for line in lines:
                        if '#[test]' in line:
                            in_test = True
                            rust_tests.append((file_path, line.strip()))
                        elif in_test and line.strip().startswith('fn'):
                            rust_tests.append((file_path, line.strip()))
                            in_test = False
                        elif in_test:
                            rust_tests.append((file_path, line.strip()))

    return rust_tests


def main():
    directory = r"C:\Users\scmacdon\TestGit\aws-doc-sdk-examples\rustv1"
    rust_tests = find_rust_tests(directory)

    if rust_tests:
        print("Found Rust tests:")
        for file_path, test_line in rust_tests:
            print(f"File: {file_path}")
            print(f"  Test: {test_line}")
            print()
    else:
        print("No Rust tests found.")


if __name__ == "__main__":
    main()
