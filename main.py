import os
import json
import argparse
from PIL import Image
from tqdm import tqdm
import math

class Packer:
    def __init__(self, width, height):
        self.root = {"x": 0, "y": 0, "w": width, "h": height}

    def fit(self, blocks):
        for block in blocks:
            node = self.find_node(self.root, block.w, block.h)
            if node:
                block.fit = self.split_node(node, block.w, block.h)
            else:
                block.fit = None

    def find_node(self, root, width, height):
        if root.get("used"):
            return self.find_node(root.get("right"), width, height) or self.find_node(root.get("down"), width, height)
        elif width <= root["w"] and height <= root["h"]:
            return root
        else:
            return None

    def split_node(self, node, width, height):
        node["used"] = True
        node["down"] = {"x": node["x"], "y": node["y"] + height, "w": node["w"], "h": node["h"] - height}
        node["right"] = {"x": node["x"] + width, "y": node["y"], "w": node["w"] - width, "h": height}
        return node

class Block:
    def __init__(self, width, height, filename, texture_image, subtextures):
        self.w = width
        self.h = height
        self.filename = filename
        self.texture_image = texture_image
        self.subtextures = subtextures  # Added for storing subtexture data
        self.fit = None  # Position data will be set after packing

def pack_squares(squares, container_size):
    # sort by min side length
    squares.sort(key=lambda square_data: min(square_data[1] , square_data[2]), reverse=True)  
    containers = []  # Initialize containers list
    square_positions = []

    for square_data in tqdm(squares, desc="Packing textures"):
        filename, width, height, texture_image, subtextures = square_data
        if width > container_size or height > container_size:
            print(f"error the image {filename} has dimensions {width}x{height}, but the container is {container_size}x{container_size}, make the container size bigger")
        block = Block(width, height, filename, texture_image, subtextures)
        placed = False

        for packer, container_image in containers:
            packer.fit([block])
            if block.fit:
                x, y = block.fit["x"], block.fit["y"]
                container_image.paste(texture_image, (x, y))

                # Adjust subtexture positions
                if block.subtextures:
                    for subtexture_name, subtexture_data in block.subtextures.items():
                        subtexture_data["x"] += x
                        subtexture_data["y"] += y
                square_positions.append((len(containers) - 1, x, y, width, block.subtextures))
                placed = True
                break

        if not placed:
            # Create a new container if the current block doesn't fit in any existing ones
            new_packer = Packer(container_size, container_size)
            new_container_image = Image.new('RGBA', (container_size, container_size), (0, 0, 0, 0))
            new_packer.fit([block])

            if block.fit:
                x, y = block.fit["x"], block.fit["y"]
                new_container_image.paste(texture_image, (x, y))
                square_positions.append((len(containers), x, y, width, block.subtextures))

            containers.append((new_packer, new_container_image))

    return containers, square_positions

def collect_textures_data(directory):
    """Collect valid square texture data from a directory, along with any subtexture metadata."""
    textures_data = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(root, file)
                with Image.open(file_path) as img:

                    width, height = img.size
                    if is_power_of_two(width) and is_power_of_two(height):
                        subtextures = {}

                        # Check for associated JSON file
                        json_path = os.path.splitext(file_path)[0] + ".json"
                        if os.path.exists(json_path):
                            with open(json_path, 'r') as json_file:
                                subtextures = json.load(json_file).get("sub_textures", {})

                        # Append data including the full file path
                        print(f"found texture {file_path} with dimensions {width}x{height}")
                        textures_data.append((file_path, width, height, img.copy(), subtextures))
                    else:
                        print(f"the texture {file_path} did not have a power of two dimensions")
    return textures_data

def is_power_of_two(n):
    return n > 0 and (n & (n - 1)) == 0

def main():
    parser = argparse.ArgumentParser(description="Pack textures into a larger image and generate JSON metadata.")
    parser.add_argument("textures_directory", help="Path to the directory containing textures")
    parser.add_argument("--output_json", "-o", type=str, default="packed_texture.json", help="Output JSON file path")
    parser.add_argument("--output_dir", "-d", type=str, default="packed_textures", help="Directory to save packed textures and images (default: packed textures)")
    parser.add_argument("--packed_texture_size","-s", type=int, default=1024, help="Size of the image to pack textures into, it packs into a square of a power of two, this argument is the size of the square along with and height (default: 1024)")
    args = parser.parse_args()

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    print("Scanning for textures...")
    textures_data = collect_textures_data(args.textures_directory)
    print("Packing textures...")
    containers, packed_positions = pack_squares(textures_data, args.packed_texture_size)

    # Prepare JSON data
    sub_textures = {}
    for (filename, width, height, _, original_subtextures), (container_idx, x, y, _, updated_subtextures) in zip(textures_data, packed_positions):
        sub_textures[filename] = {
            "container_index": container_idx,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "sub_textures": updated_subtextures  # Include updated subtexture positions
        }

    result = {"sub_textures": sub_textures}

    # Write JSON metadata to the specified output directory
    json_output_path = os.path.join(args.output_dir, args.output_json)
    with open(json_output_path, 'w') as json_file:
        json.dump(result, json_file, indent=4)
    print(f"Metadata saved to {json_output_path}")

    for index, (_, container_image) in enumerate(containers):
        output_path = os.path.join(args.output_dir, f"packed_texture_{index}.png")
        container_image.save(output_path)
        print(f"Saved container image to {output_path}")

if __name__ == "__main__":
    main()
