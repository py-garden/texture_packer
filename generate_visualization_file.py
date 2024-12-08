import os
import json
import cv2
import argparse
import numpy as np


def draw_atlas_visualization(image_path, json_data, container_images):
    """
    Draw rectangles from JSON data on the image and annotate with names.
    Rectangles on the first level are drawn with transparency and background colors,
    while the colors change with each iteration over the first level.
    """
    # Load the base image
    image = cv2.imread(image_path)

    # Define a list of colors for first-level rectangles
    first_level_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255)]
    color_index = 0  # To cycle through colors for first-level rectangles

    # Draw the first level rectangles (direct sub_textures)
    for key, rect in json_data['sub_textures'].items():
        # Extract container index and select the corresponding container image
        container_index = rect.get('container_index', 0)
        container_image = container_images[container_index]

        # Coordinates and size of the sub-texture
        x, y, width, height = rect['x'], rect['y'], rect['width'], rect['height']
        
        # Get the color for the current rectangle (from the predefined list)
        color = first_level_colors[color_index % len(first_level_colors)]  # Cycle colors

        # First level rectangles (with background color and transparency)
        overlay = container_image.copy()  # Make a copy to apply the transparent overlay
        alpha = 0.5  # Set transparency (0 = fully transparent, 1 = fully opaque)
        
        # Create a filled rectangle with background color
        cv2.rectangle(overlay, (int(x), int(y)), (int(x + width), int(y + height)), color, -1)
        
        # Blend the overlay with the original image (this adds transparency)
        cv2.addWeighted(overlay, alpha, container_image, 1 - alpha, 0, container_image)

        # Annotate with the key (name) of the rectangle
        cv2.putText(container_image, key, (int(x), int(y) + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        # Check for second-level sub-textures
        if 'sub_textures' in rect:
            for sub_key, sub_rect in rect['sub_textures'].items():
                sub_x, sub_y, sub_width, sub_height = sub_rect['x'], sub_rect['y'], sub_rect['width'], sub_rect['height']
                
                # Second level rectangles (solid green color with thickness 2)
                cv2.rectangle(container_image, (int(sub_x), int(sub_y)),
                              (int(sub_x + sub_width), int(sub_y + sub_height)), (0, 255, 0), 2)
                
                # Annotate with the sub_key (name) of the second-level rectangle
                cv2.putText(container_image, sub_key, (int(sub_x), int(sub_y) + 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

        # Update the color index for the next rectangle
        color_index += 1

    return container_images

def process_directory(directory):
    """
    Recursively find JSON files and corresponding image files. Handles multiple containers.
    """
    container_images = []
    
    # Load all container images first
    for root, dirs, files in os.walk(directory):
        image_files = [f for f in files if f.endswith('.png')]
        for image_file in image_files:
            image_path = os.path.join(root, image_file)
            container_images.append(cv2.imread(image_path))

    # Now process JSON files
    for root, dirs, files in os.walk(directory):
        json_files = [f for f in files if f.endswith('.json')]
        
        for json_file in json_files:
            json_path = os.path.join(root, json_file)

            # Read the JSON data
            with open(json_path, 'r') as f:
                json_data = json.load(f)

            print(f"Processing {json_file}")
            
            # Draw the atlas visualization
            container_images = draw_atlas_visualization(json_path, json_data, container_images)

            # Save the result (saving all container images)
            for idx, container_image in enumerate(container_images):
                output_path = os.path.join(root, f"container_{idx}_atlas_visualization.png")
                cv2.imwrite(output_path, container_image)
                print(f"Saved visualization to {output_path}")
    
def main():
    parser = argparse.ArgumentParser(description="Packed Texture Visualizer: Annotate images with rectangles from JSON files.")
    parser.add_argument('directory', type=str, help="The directory to search for JSON files and corresponding images.")
    args = parser.parse_args()
    
    process_directory(args.directory)

if __name__ == '__main__':
    main()
