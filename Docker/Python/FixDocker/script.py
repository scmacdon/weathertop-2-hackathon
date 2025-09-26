import os

def main():
    # Path to your file
    path = "C:\\Users\\scmacdon\\Docker\\Python\\Dockerfile.txt"

    # New correct name
    new_path = os.path.join(os.path.dirname(path), "Dockerfile")

    # Rename the file
    os.rename(path, new_path)
    print(f"Renamed to {new_path}")

if __name__ == "__main__":
    main()

