---
annotations_creators: []
language: en
size_categories:
- n<1K
task_categories:
- object-detection
task_ids: []
pretty_name: graspclutter6d
tags:
- fiftyone
- group
- object-detection
dataset_summary: >




  This is a [FiftyOne](https://github.com/voxel51/fiftyone) dataset with 111
  samples.


  ## Installation


  If you haven't already, install FiftyOne:


  ```bash

  pip install -U fiftyone

  ```


  ## Usage


  ```python

  import fiftyone as fo

  from fiftyone.utils.huggingface import load_from_hub


  # Load the dataset

  # Note: other available arguments include 'max_samples', etc

  dataset = load_from_hub("Voxel51/graspclutter6d")


  # Launch the App

  session = fo.launch_app(dataset)

  ```
license: cc-by-sa-4.0
---

# Dataset Card for graspclutter6d

![image/png](graspclutter6d.gif)

GraspClutter6D is a large-scale real-world dataset for robust perception and grasping in cluttered scenes. This FiftyOne dataset contains a **curated subset** of 99 scenes from the full GraspClutter6D dataset, optimized for visualization and exploration.



This is a [FiftyOne](https://github.com/voxel51/fiftyone) dataset with 111 samples.

## Installation

If you haven't already, install FiftyOne:

```bash
pip install -U fiftyone
```

## Usage

```python
import fiftyone as fo
from huggingface_hub import snapshot_download

# Download the dataset snapshot to the current working directory
snapshot_download(
    repo_id="Voxel51/graspclutter6d", 
    local_dir=".", 
    repo_type="dataset"
    )

# Load dataset from current directory using FiftyOne's native format
dataset = fo.Dataset.from_dir(
    dataset_dir=".",  # Current directory contains the dataset files
    dataset_type=fo.types.FiftyOneDataset,  # Specify FiftyOne dataset format
    name="graspclutter6d"  # Assign a name to the dataset for identification
)

# Launch the App
session = fo.launch_app(dataset)
```

### Dataset Description


**This Subset** (demo):
- 99 scenes spanning the occlusion range (selected by visibility distribution)
- ~400 RGB-D images (most scenes have 1 viewpoint = 4 camera views)
- 200 object models (.ply meshes)
- Grasp annotations for hero scene objects only (~14 objects)

- **Curated by:** Seunghyeok Back, Joosoon Lee, Kangmin Kim, Heeseon Rho, Geonhyup Lee, Raeyoung Kang, Sangbeom Lee, Sangjun Noh, Youngjin Lee, Taeyeop Lee, and Kyoobin Lee
- **Funded by :** Korea Institute of Machinery & Materials (KIMM), Gwangju Institute of Science and Technology (GIST), Korea Advanced Institute of Science and Technology (KAIST)
- **License:** Creative Commons Attribution Share Alike 4.0 

### Dataset Sources 

- **Repository:** https://huggingface.co/datasets/GraspClutter6D/GraspClutter6D
- **Paper:** https://arxiv.org/abs/2504.06866
- **Project Website:** https://sites.google.com/view/graspclutter6d

## Uses

### Direct Use

This dataset is intended for:
- **Research and development** of robotic grasping systems in cluttered environments
- **Training and evaluation** of computer vision models for:
  - Instance segmentation in heavy occlusion
  - 6D object pose estimation
  - Grasp detection and planning
- **Benchmarking** perception algorithms against highly cluttered real-world scenarios
- **Visual exploration** of multi-camera RGB-D data with depth maps and 3D reconstructions
- **Educational purposes** to understand challenges in robotic perception

### Out-of-Scope Use

This demo subset (99 scenes) is optimized for visualization and exploration in FiftyOne, not for training large-scale models. For model training, use the full GraspClutter6D dataset from HuggingFace.

## Dataset Structure

### FiftyOne Dataset Organization

This dataset is organized as a **grouped dataset** in FiftyOne, where each group represents one scene-viewpoint combination.

**Group Structure:**
Each group has **5 slices**:
- `realsense_d415`: RGB-D images from RealSense D415 camera
- `realsense_d435`: RGB-D images from RealSense D435 camera  
- `azure_kinect`: RGB-D images from Azure Kinect camera
- `zivid`: RGB-D images from Zivid camera
- `3d`: 3D scene reconstruction with object meshes

**Camera Resolutions:**
- RealSense D415/D435: 1920 × 1080
- Azure Kinect: 3840 × 2160
- Zivid: 1920 × 1200

### Sample Fields (2D Camera Slices)

| Field | Type | Description |
|-------|------|-------------|
| `scene_id` | str | Scene identifier (e.g., "000109") |
| `camera` | str | Camera name (realsense_d415, realsense_d435, azure_kinect, zivid) |
| `viewpoint` | int | Viewpoint index (0-12, most scenes have only 0) |
| `image_id` | int | BOP dataset image ID |
| `num_objects` | int | Number of objects in scene |
| `mean_visibility` | float | Mean visibility fraction across all objects [0-1] |
| `depth_scale_mm` | float | Scale factor to convert depth values to millimeters |
| `depth` | Heatmap | Depth map with values in millimeters (16-bit, scaled) |
| `detections` | Detections | 2D bounding boxes with instance masks and visibility metrics |
| `grasp_lines` | Polylines | Grasp approach directions (contact point + 50mm approach vector) |

**Detection Fields** (per object instance):
- `label`: Object ID (e.g., "obj_066")
- `bounding_box`: Normalized [x, y, w, h] coordinates [0-1]
- `mask`: Instance segmentation mask (cropped to bbox)
- `obj_id`: Object type ID
- `instance_idx`: Instance index in scene
- `visib_fract`: Visible fraction of object [0-1]
- `px_count_visib`: Number of visible pixels
- `px_count_valid`: Number of valid pixels
- `px_count_all`: Total pixel count

**Grasp Line Fields** (per grasp, hero scene only):
- `label`: Object ID (e.g., "grasp_obj_066")
- `points`: Two points [[x1,y1], [x2,y2]] - contact point and tip (50mm along approach)
- `obj_id`: Object type ID
- `grasp_score`: Grasp quality score [0-1]

### Sample Fields (3D Scene Slice)

| Field | Type | Description |
|-------|------|-------------|
| `scene_id` | str | Scene identifier |
| `viewpoint` | int | Viewpoint index |
| `filepath` | str | Path to .fo3d scene file |
| `detections` | Detections | 3D axis-aligned bounding boxes |

**3D Detection Fields** (per object):
- `label`: Object ID
- `location`: [x, y, z] box center in camera coordinates (mm)
- `dimensions`: [width, length, height] in mm
- `rotation`: [0, 0, 0] (axis-aligned bounding boxes)
- `obj_id`: Object type ID

## Dataset Creation

### Curation Rationale

The full GraspClutter6D dataset was created to address the gap between existing benchmark datasets and real-world cluttered grasping scenarios. Most existing datasets feature simple scenes with light occlusion (~35% in GraspNet-1B), while real warehouse and manufacturing environments contain densely packed objects with heavy occlusion (62.6% in this dataset).

This demo subset was curated to:
- Provide a manageable dataset size (~3-8 GB) for visualization and exploration
- Span the full range of occlusion levels (easy to hard)
- Include one detailed "hero" scene with multiple viewpoints for in-depth analysis
- Enable quick prototyping and algorithm development

### Source Data

#### Data Collection and Processing

**Capture Setup:**
- 4 RGB-D cameras: RealSense D415, RealSense D435, Azure Kinect, Zivid
- Multiple viewpoints per scene (up to 13)
- Scenes arranged in bins, shelves, and tables with natural backgrounds
- 200 objects with varied shapes, sizes, textures, and materials

**Annotations:**
- 6D object poses obtained through multi-view optimization
- Instance segmentation masks from visible pixel analysis  
- Grasp annotations computed using GraspNet framework with collision detection

**This Subset Processing:**
- Downloaded from HuggingFace using `snapshot_download`
- Extracted from 7z archives (~207 GB compressed)
- Stratified sampling by occlusion level
- Pruned to 99 scenes, 200 object models, hero scene grasp labels
- Final size: ~3-8 GB

#### Who are the source data producers?

Research teams from:
- Korea Institute of Machinery & Materials (KIMM)
- Gwangju Institute of Science and Technology (GIST)  
- Korea Advanced Institute of Science and Technology (KAIST)

Data collected through robotic capture systems and annotated using a combination of automated methods and crowd-sourcing.

### Annotations 

#### Annotation process

**6D Object Poses:**
- Computed using multi-view bundle adjustment
- Refined through iterative closest point (ICP) alignment
- Validated against depth data

**Instance Segmentation:**
- Generated from depth discontinuities and object models
- Per-instance masks provided for visible regions
- Visibility metrics computed (visib_fract, px_count_visib, etc.)

**Grasp Annotations:**
- Generated using GraspNet antipodal grasp sampling
- ~18 million candidate grasps per object tested
- Collision detection performed in simulation
- Quality scores computed based on force closure metrics
- Only collision-free, high-quality grasps retained

**This Subset:**
- All annotations inherited from full dataset
- Grasp annotations only retained for hero scene objects

#### Who are the annotators?

Annotations were produced through:
- Automated pose estimation algorithms (multi-view optimization)
- Simulation-based grasp generation (GraspNet framework)
- Quality validation by research team

## Citation 

**BibTeX:**

```bibtex
@article{back2025graspclutter6d,
  title={GraspClutter6D: A Large-scale Real-world Dataset for Robust Perception and Grasping in Cluttered Scenes},
  author={Back, Seunghyeok and Lee, Joosoon and Kim, Kangmin and Rho, Heeseon and Lee, Geonhyup and Kang, Raeyoung and Lee, Sangbeom and Noh, Sangjun and Lee, Youngjin and Lee, Taeyeop and Lee, Kyoobin},
  journal={arXiv preprint arXiv:2504.06866},
  year={2025}
}
```

**APA:**

Back, S., Lee, J., Kim, K., Rho, H., Lee, G., Kang, R., Lee, S., Noh, S., Lee, Y., Lee, T., & Lee, K. (2025). GraspClutter6D: A Large-scale Real-world Dataset for Robust Perception and Grasping in Cluttered Scenes. arXiv preprint arXiv:2504.06866.


## More Information 

**Project Website**: https://sites.google.com/view/graspclutter6d

**Full Dataset**: https://huggingface.co/datasets/GraspClutter6D/GraspClutter6D

**Paper**: https://arxiv.org/abs/2504.06866

Original dataset by: Seunghyeok Back, Joosoon Lee, Kangmin Kim, Heeseon Rho, Geonhyup Lee, Raeyoung Kang, Sangbeom Lee, Sangjun Noh, Youngjin Lee, Taeyeop Lee, and Kyoobin Lee

## Dataset Card Contact

For questions about the full GraspClutter6D dataset: kyoobinlee@gist.ac.kr