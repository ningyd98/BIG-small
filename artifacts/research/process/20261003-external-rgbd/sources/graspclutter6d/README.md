---
language:
- en
license: cc-by-sa-4.0
size_categories:
- n>1T
task_categories:
- object-detection
- image-segmentation
- robotics
pretty_name: GC6D
tags:
- robot
---

# GraspClutter6D Dataset

[GraspClutter6D: A Large-scale Real-world Dataset for Robust Perception and Grasping in Cluttered Scenes](https://arxiv.org/abs/2504.06866)

[Seunghyeok Back](http://backseunghyeok.com/), Joosoon Lee, Kangmin Kim, Heeseon Rho, Geonhyup Lee, Raeyoung Kang, Sangbeom Lee, Sangjun Noh, Youngjin Lee, Taeyeop Lee, Kyoobin Lee

Accepted at IEEE Robotics and Automation Letters (RA-L)

[[ArXiv]](https://arxiv.org/abs/2504.06866) [[Project Website]](https://sites.google.com/view/graspclutter6d/) [[Video]](https://youtu.be/NkKkfVS5wZ4) [[Dataset Format]](https://sites.google.com/view/graspclutter6d/dataset) [[GitHub]](https://github.com/SeungBack/graspclutter6dAPI.git)

To download the dataset, run the following commands:
```bash
mkdir GraspClutter6D && cd GraspClutter6D
export SRC=https://huggingface.co/datasets/GraspClutter6D/GraspClutter6D/resolve/main

# scene data
wget $SRC/split_info.7z
wget $SRC/scenes.7z.001
wget $SRC/scenes.7z.002
wget $SRC/scenes.7z.003
wget $SRC/scenes.7z.004
wget $SRC/scenes.7z.005
7z x split_info.7z
7z x scenes.7z.001

# for object pose estimation
wget $SRC/models.7z
wget $SRC/models_eval.7z
wget $SRC/models_obj.7z
wget $SRC/models_obj_eval.7z

7z x models.7z
7z x models_eval.7z
7z x models_obj.7z
7z x models_obj_eval.7z

# for grasp detection
wget $SRC/grasp_label.7z
wget $SRC/collision_label.7z
wget $SRC/dex_models.7z
wget $SRC/models_m.7z
wget $SRC/models_obj_m.7z

7z x grasp_label.7z
7z x collision_label.7z
7z x dex_models.7z
7z x models_m.7z
7z x models_obj_m.7z
```

### Dataset Toolkit Usage

This dataset comes with a Python API and toolkit (`graspclutter6dAPI`) to facilitate loading, manipulating, and evaluating 6D grasp pose annotations.

**Installation:**

You can install the toolkit via pip:

```bash
pip install graspclutter6dAPI
```

Alternatively, install from source:

```bash
conda create -n gc6d python=3.8
conda activate gc6d
git clone https://github.com/SeungBack/graspclutter6dAPI.git
cd graspclutter6dAPI
pip install -e .
```

**Environment Setup:**

Before running examples, set the `GC6D_ROOT` environment variable to your dataset location:

```bash
export GC6D_ROOT='/path/to/graspclutter6d'
```

**Usage Examples:**

*   **Validate Dataset Integrity:**
    ```bash
    python examples/exam_check_data.py
    ```
*   **Load Grasp Annotations:**
    ```bash
    python examples/exam_loadGrasp.py
    ```
*   **Visualize Grasp Annotations:**
    ```bash
    python examples/exam_vis.py
    ```