from __future__ import annotations
import os
import json
import argparse
from PIL import Image
from tqdm import tqdm
import math
from typing import List, Tuple, Optional, Set
from dataclasses import dataclass
import pickle
import re

def save_packed_state(packed_textures: List[PackedTexture], packed_texture_indices: List[PackedTextureIndex], output_dir: str):
    packed_state = {
        "packed_textures": [(pt.packer.root, pt.image) for pt in packed_textures],
        "packed_texture_indices": packed_texture_indices,
    }
    with open(os.path.join(output_dir, "packed_state.pkl"), "wb") as file:
        pickle.dump(packed_state, file)
    print(f"Packed state saved to {os.path.join(output_dir, 'packed_state.pkl')}")

def load_packed_state(file_path: str) -> Tuple[List[PackedTexture], List[PackedTextureIndex]]:
    with open(file_path, "rb") as file:
        packed_state = pickle.load(file)
    packed_textures = [
        PackedTexture(Packer(pt[0].w, pt[0].h), pt[1]) for pt in packed_state["packed_textures"]
    ]
    packed_texture_indices = packed_state["packed_texture_indices"]
    return packed_textures, packed_texture_indices

@dataclass
class PackedNode:
    x: int
    y: int
    w: int
    h: int
    used: bool = False
    left: Optional[PackedNode] = None
    right: Optional[PackedNode] = None

class Packer:
    def __init__(self, width: int, height: int):
        self.root = PackedNode(0, 0, width, height)

    def fit(self, blocks: List[Block]):
        for block in blocks:
            node = self.find_node(self.root, block.w, block.h)
            if node:
                block.packed_placement = self.split_node(node, block.w, block.h)
            else:
                block.packed_placement = None

    def find_node(self, root: Optional[PackedNode], width: int, height: int) -> Optional[PackedNode]:
        if root is None:
            return None
        if root.used:
            return (
                self.find_node(root.right, width, height)
                or self.find_node(root.left, width, height)
            )
        elif width <= root.w and height <= root.h:
            return root
        else:
            return None

    def split_node(self, node: PackedNode, width: int, height: int) -> PackedNode:
        node.used = True
        node.right = PackedNode(node.x + width, node.y, node.w - width, height)
        node.left = PackedNode(node.x, node.y + height, node.w, node.h - height)
        return node

@dataclass
class PackedTexture:
    packer: Packer
    image: Image.Image

@dataclass
class PackedTextureIndex:
    packed_index: int
    top_left_corner_x: int
    top_left_corner_y: int
    packed_subtextures: dict[str, dict[str, float]]


@dataclass
class Block:
    w: int
    h : int
    filename : str
    texture_image : Image.Image
    subtextures: dict[str, dict[str, float]] 
    packed_placement = Optional[PackedNode]

def pack_texture_blocks(texture_blocks: List[Block], container_size: int) -> Tuple[List[PackedTexture], List[PackedTextureIndex]]:
    # sort by min side length
    texture_blocks.sort(key=lambda block: min(block.w , block.h), reverse=True)  

    currently_created_packed_textures : List[PackedTexture] = []  
    packed_texture_indices : List[PackedTextureIndex] = []

    for block in tqdm(texture_blocks, desc="Packing textures"):
        if block.w > container_size or block.h > container_size:
            print(f"error the image {block.filename} has dimensions {block.w}x{block.h}, but the container is {container_size}x{container_size}, make the container size bigger")

        placed = False

        # on the first iteration there are no containers
        for pt in currently_created_packed_textures:
            pt.packer.fit([block])
            if block.packed_placement:
                x, y = block.packed_placement.x, block.packed_placement.y
                pt.image.paste(block.texture_image, (x, y))

                # Adjust subtexture positions
                if block.subtextures:
                    for subtexture_name, subtexture_data in block.subtextures.items():
                        subtexture_data["x"] += x
                        subtexture_data["y"] += y

                packed_texture_index = PackedTextureIndex(len(currently_created_packed_textures) - 1, x, y, block.subtextures)
                packed_texture_indices.append(packed_texture_index)
                placed = True
                break

        if not placed:
            # Create a new container if the current block doesn't fit in any existing ones
            new_packer = Packer(container_size, container_size)
            new_container_image = Image.new('RGBA', (container_size, container_size), (0, 0, 0, 0))
            new_packer.fit([block])

            if block.packed_placement:
                x, y = block.packed_placement.x, block.packed_placement.y
                new_container_image.paste(block.texture_image, (x, y))

                packed_texture_index = PackedTextureIndex(len(currently_created_packed_textures) , x, y, block.subtextures)
                packed_texture_indices.append(packed_texture_index)

            pt = PackedTexture(new_packer, new_container_image)
            currently_created_packed_textures.append(pt)

    return currently_created_packed_textures, packed_texture_indices

def collect_textures_data_from_dir(directory, output_dir, currently_packed_texture_paths) -> List[Block]:
    """
    Collect valid square texture data from a directory, along with any subtexture metadata.
    Avoids textures generated by the script (e.g., packed_texture_*.png) and already processed textures.
    
    Args:
        directory (str): The directory to scan for textures.
        output_dir (str): The directory where generated textures are stored.
        processed_files (set): A set of file paths that have already been processed.
    
    Returns:
        List[Block]: A list of valid textures as Block objects.
    """
    
    # Regular expression to match generated texture names
    generated_pattern = re.compile(r"^packed_texture_\d+\.png$")

    image_file_paths = []
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(root, file)
                
                # Skip files generated by the script
                if generated_pattern.match(file) and os.path.samefile(root, output_dir):
                    print(f"Skipping generated texture file: {file}")
                    continue
                
                # Skip already processed files
                if file_path in currently_packed_texture_paths:
                    print(f"Skipping already processed texture file: {file_path}")
                    continue

                image_file_paths.append(file_path)

    return collect_textures_data(image_file_paths, currently_packed_texture_paths)

def collect_textures_data(image_file_paths: List[str], currently_packed_texture_paths: Set[str]) -> List[Block]:

    textures_data: List[Block] = []
                
    for file_path in image_file_paths:
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
                print(f"Found texture {file_path} with dimensions {width}x{height}")
                block = Block(width, height, file_path, img.copy(), subtextures)
                textures_data.append(block)
                
                # Add the file to the processed set
                currently_packed_texture_paths.add(file_path)
            else:
                print(f"The texture {file_path} did not have power-of-two dimensions")
    
    return textures_data

def is_power_of_two(n):
    return n > 0 and (n & (n - 1)) == 0

def main():
    parser = argparse.ArgumentParser(description="Pack textures into a larger image and generate JSON metadata.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--textures_directory", "-t", help="Path to the directory containing textures")
    group.add_argument("--texture_paths_file", "-f", help="Path to a file containing the list of texture paths")
    parser.add_argument("--output_dir", "-d", type=str, default="packed_textures",
                        help="Directory to save packed textures and images (default: packed_textures)")
    parser.add_argument("--packed_texture_size", "-s", type=int, default=1024,
                        help="Size of the image to pack textures into, in pixels (default: 1024)")
    parser.add_argument("--append", "-a", action="store_true",
                        help="Continue packing using an existing packed state if available")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    if args.append and os.path.exists(os.path.join(args.output_dir, "packed_state.pkl")):
        print("Loading existing packed state...")
        currently_created_packed_textures, packed_texture_indices = load_packed_state(
            os.path.join(args.output_dir, "packed_state.pkl")
        )
    else:
        currently_created_packed_textures = []
        packed_texture_indices = []

    def load_processed_files(file_path):
        """Load processed file paths from a file."""
        try:
            with open(file_path, "r") as f:
                return set(line.strip() for line in f if line.strip())
        except FileNotFoundError:
            return set()

    currently_packed_texture_paths_file = os.path.join(args.output_dir, "currently_packed_texture_paths.txt")

    if args.append:
        print("Loading previously processed textures...")
        currently_packed_texture_paths = load_processed_files(currently_packed_texture_paths_file)
    else:
        currently_packed_texture_paths = set()

    print("Collecting texture paths...")
    if args.textures_directory:
        texture_blocks = collect_textures_data_from_dir(args.textures_directory, args.output_dir, currently_packed_texture_paths)
    elif args.texture_paths_file:
        try:
            with open(args.texture_paths_file, "r") as file:
                texture_paths = [line.strip() for line in file if line.strip()]
            # texture_blocks = collect_textures_data(texture_paths, args.output_dir, currently_packed_texture_paths, from_file=True)
            texture_blocks = collect_textures_data(texture_paths, currently_packed_texture_paths)
        except FileNotFoundError:
            print(f"Error: The file {args.texture_paths_file} does not exist.")
            return

    print("Packing textures...")

    with open(currently_packed_texture_paths_file, "w") as f:
        for file_path in currently_packed_texture_paths:
            f.write(file_path + "\n")

    packed_textures, new_packed_texture_indices = pack_texture_blocks(
        texture_blocks, args.packed_texture_size
    )
    currently_created_packed_textures.extend(packed_textures)
    packed_texture_indices.extend(new_packed_texture_indices)

    save_packed_state(currently_created_packed_textures, packed_texture_indices, args.output_dir)

    sub_textures = {}
    for block, packed_texture_index in zip(texture_blocks, new_packed_texture_indices):
        sub_textures[block.filename] = {
            "container_index": packed_texture_index.packed_index,
            "x": packed_texture_index.top_left_corner_x,
            "y": packed_texture_index.top_left_corner_y,
            "width": block.w,
            "height": block.h,
            "sub_textures": packed_texture_index.packed_subtextures,
        }

    result = {"sub_textures": sub_textures}

    json_output_path = os.path.join(args.output_dir, "packed_texture.json")
    with open(json_output_path, 'w') as json_file:
        json.dump(result, json_file, indent=4)
    print(f"Metadata saved to {json_output_path}")

    for index, packed_texture in enumerate(currently_created_packed_textures):
        output_path = os.path.join(args.output_dir, f"packed_texture_{index}.png")
        packed_texture.image.save(output_path)
        print(f"Saved container image to {output_path}")

if __name__ == "__main__":
    main()
