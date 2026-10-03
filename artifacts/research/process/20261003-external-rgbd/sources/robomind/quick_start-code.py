!pip install numpy
!pip install opencv-python
!pip install h5py
!pip install imageio


 
import numpy as np
import os
import cv2
import copy
import argparse
import imageio
import h5py
import cv2
from collections import defaultdict
from IPython.display import Image, display
import argparse

RESOLUTION = (128, 128)


class ReadH5Files():
    def __init__(self, robot_infor):
        self.camera_names = robot_infor['camera_names']
        self.camera_sensors = robot_infor['camera_sensors']
        self.arms = robot_infor['arms']
        self.robot_infor = robot_infor['controls']

    def decoder_image(self, camera_rgb_images, camera_depth_images):
        if type(camera_rgb_images[0]) is np.uint8:
            rgb = cv2.imdecode(camera_rgb_images, cv2.IMREAD_COLOR)
            if camera_depth_images is not None:
                depth_array = np.frombuffer(camera_depth_images, dtype=np.uint8)
                depth = cv2.imdecode(depth_array, cv2.IMREAD_UNCHANGED)
            else:
                depth = np.asarray([])
            return rgb, depth
        else:
            rgb_images = []
            depth_images = []
            for idx, camera_rgb_image in enumerate(camera_rgb_images):
                camera_rgb_image = np.array(camera_rgb_image)
                # print(f"camera_rgb_image: {camera_rgb_image.shape}")
                rgb = cv2.imdecode(camera_rgb_image, cv2.IMREAD_COLOR)
                if rgb is None:
                    rgb = np.frombuffer(camera_rgb_image, dtype=np.uint8)
                    if rgb.size == 2764800:
                        rgb = rgb.reshape(720, 1280, 3)
                    elif rgb.size == 921600:
                        rgb = rgb.reshape(480, 640, 3)
                if camera_depth_images is not None:
                    # print(f"camera_depth_images shape: {camera_depth_images[idx].shape}")
                    depth_array = np.frombuffer(camera_depth_images[idx], dtype=np.uint8)
                    depth = cv2.imdecode(depth_array, cv2.IMREAD_UNCHANGED)
                    if depth is None:
                        # print(f"camera_depth_images shape: {camera_depth_images[idx].shape}")
                        depth = np.frombuffer(camera_depth_images[idx], dtype=np.uint8)
                        if depth.size == 921600:
                            depth = depth.reshape(720, 1280)
                        elif depth.size == 307200:
                            depth = depth.reshape(480, 640)
                            
                else:
                    depth = np.asarray([])
                rgb_images.append(rgb)
                depth_images.append(depth)
            rgb_images = np.asarray(rgb_images)
            depth_images = np.asarray(depth_images)
            return rgb_images, depth_images

    def execute(self, file_path, camera_frame=None, control_frame=None):
        with h5py.File(file_path, 'r') as f:
            is_sim = f.attrs['sim']
            is_compress = f.attrs['compress']
            is_compress = True
            image_dict = defaultdict(dict)
            for cam_name in self.camera_names:
                if is_compress:
                    if camera_frame is not None:
                        if len(self.camera_sensors) >= 2:
                            decode_rgb, decode_depth = self.decoder_image(
                                camera_rgb_images=f['observations'][self.camera_sensors[0]][cam_name][camera_frame],
                                    camera_depth_images=f['observations'][self.camera_sensors[1]][cam_name][camera_frame])
                        else:
                            decode_rgb, decode_depth = self.decoder_image(
                                camera_rgb_images=f['observations'][self.camera_sensors[0]][cam_name][camera_frame],
                                camera_depth_images=None)
                    else:
                        if len(self.camera_sensors) >= 2:
                            ## print camera_sensors keys and camera_keys if needed for debugging
                            # print(f"camera_sensors keys: {f['observations'].keys()}")
                            # print(f"camera_keys: {f['observations'][self.camera_sensors[0]].keys()}")
                            rgb_images = f['observations'][self.camera_sensors[0]][cam_name][:]
                            depth_images = f['observations'][self.camera_sensors[1]][cam_name][:]
                        else:
                            rgb_images = f['observations'][self.camera_sensors[0]][cam_name][:]
                            depth_images = None
                        print(f"rgb_images: {rgb_images.shape}")
                        print(f"depth_images: {depth_images.shape if depth_images is not None else 'None'}")
                        decode_rgb, decode_depth = self.decoder_image(camera_rgb_images=rgb_images,camera_depth_images=depth_images)
                    
                    image_dict[self.camera_sensors[0]][cam_name] = decode_rgb
                    if len(self.camera_sensors) >= 2:
                        image_dict[self.camera_sensors[1]][cam_name] = decode_depth

                else:
                    if camera_frame:
                        image_dict[self.camera_sensors[0]][cam_name] = f[
                            'observations'][self.camera_sensors[0]][cam_name][camera_frame]
                        image_dict[self.camera_sensors[1]][cam_name] = f[
                            'observations'][self.camera_sensors[1]][cam_name][camera_frame]
                    else:
                        image_dict[self.camera_sensors[0]][cam_name] = f[
                           'observations'][self.camera_sensors[0]][cam_name][:]
                        if len(self.camera_sensors) >= 2:
                            image_dict[self.camera_sensors[1]][cam_name] = f[
                                'observations'][self.camera_sensors[1]][cam_name][:]


            control_dict = defaultdict(dict)
            for arm_name in self.arms:
                for control in self.robot_infor:
                    if control_frame:
                        control_dict[arm_name][control] = f[arm_name][control][control_frame]
                    else:
                        control_dict[arm_name][control] = f[arm_name][control][:]
            base_dict = defaultdict(dict)
        
        return image_dict, control_dict, base_dict, is_sim, is_compress




def convert_dataset_image(cur_embodiments, robot_infor, resolution=RESOLUTION, dataset_dir="realworld_data", env_names=None, save_dir='quick_start_saved_images',episode_num_pertask=2):
    read_h5files = ReadH5Files(robot_infor)

    
    for env_name in env_names:
        save_dir = f'{save_dir}/{env_name}'
        os.makedirs(save_dir, exist_ok=True)
        
        dataset_root = os.path.join(dataset_dir, env_name, 'success_episodes/train')
        cnt = 0
        for trajectory_id in sorted(os.listdir(dataset_root))[0:episode_num_pertask]:
            for file in os.listdir(os.path.join(dataset_root, trajectory_id, 'data')):
                if file.endswith('.hdf5'):
                    file_path = os.path.join(dataset_root, trajectory_id, 'data', file)
                    break
            print('executing ', cnt, 'th trajectory, file_path:', file_path)
            cnt += 1
            assert os.path.exists(file_path), f'{file_path} does not exist'
            image_dict, control_dict, base_dict, _, is_compress = read_h5files.execute(file_path)
            action_list = []
            for keys in control_dict.keys():
                control_list = []
                for control_key in control_dict[keys].keys():
                    control = control_dict[keys][control_key]
                    # in simulation, the control data may not be aligned
                    if control.shape[0] > min([control_dict[keys][k].shape[0] for k in control_dict[keys].keys()]):
                        control = control[:-1]
                    # print(f"control_key: {control_key}, control shape: {control.shape}")
                    control_list.append(control)
                control = np.concatenate(control_list, axis=1)
                action_list.append(control)
            action = np.concatenate(action_list, axis=1)
            state = copy.deepcopy(action)
            
            action = action[1:]
            state = state[0:-1]
            
            # Process images and create GIFs for each camera
            for sensor_type in image_dict.keys():
                for key in image_dict[sensor_type].keys():
                    image_dict[sensor_type][key] = image_dict[sensor_type][key][0:-1]
                for cam_name in image_dict[sensor_type].keys():
                    os.makedirs(os.path.join(save_dir, trajectory_id), exist_ok=True)
                    gif_path = os.path.join(save_dir, trajectory_id, f'{cam_name}_{sensor_type}.gif')
                    
                    # Convert images to correct color format
                    images = []
                    for step in range(len(image_dict[sensor_type][cam_name])):
                        img = np.array(image_dict[sensor_type][cam_name][step])
                        # print(f"cam_name: {cam_name}")
                        # print(img.shape)
                        if sensor_type == 'rgb_images':
                            # These embodiments image data are recorded in BGR
                            if cur_embodiments in ['h5_franka_3rgb', 'h5_franka_1rgb', 'h5_ur_1rgb', 'h5_franka_fr3_dual']:
                                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                            # Other embodiments image data are recorded in RGB  
                            else:
                                img = img
                        elif sensor_type == 'depth_images':
                            if img is not None:
                                depth_gray = img
                                # Normalize depth image to 0-255 range
                                depth_min = np.min(depth_gray)
                                depth_max = np.max(depth_gray)
                                img = ((depth_gray - depth_min) / (depth_max - depth_min) * 255).astype(np.uint8)
                                img = cv2.applyColorMap(img, cv2.COLORMAP_JET)
                                # cv2.imwrite(os.path.join(save_dir, trajectory_id, f'{cam_name}_{sensor_type}_{step:04d}.png'), img)
                            else:
                                continue  # Skip if depth image is None


                        img = cv2.resize(img, resolution, interpolation=cv2.INTER_AREA)
                        images.append(img)
                    
                    imageio.mimsave(gif_path, images, duration=0.1)  # 10 FPS
                    print(f"Saved GIF to {gif_path}")
                    # Display the GIF in the notebook
                    display(Image(filename=gif_path))
    return 





def main(args):
    env_name = args.env_name
    if args.embodiments == "h5_ur_1rgb":
        robot_infor = { 
            "camera_names": ['camera_top'], 
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['puppet'],
            "controls": ['joint_position', 'end_effector'],
            "resolution": RESOLUTION
        }
        env_name = "bread_in_basket_1" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_franka_3rgb":
        robot_infor = {
            "camera_names": ['camera_top', 'camera_left', 'camera_right'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['puppet'],
            "controls": ['joint_position', 'end_effector'],
            "resolution": RESOLUTION
        }
        env_name = "241021_close_trash_bin_1" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_franka_1rgb":
        robot_infor = {
            "camera_names": ['camera_top'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['puppet'],
            "controls": ['joint_position', 'end_effector'],
            "resolution": RESOLUTION
        }
        env_name = "bread_on_table" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_tienkung_gello_1rgb":
        robot_infor = {
            "camera_names": ['camera_top'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['puppet','master'],
            "controls": ['joint_position'],
            "resolution": RESOLUTION
        }
        env_name = "close_the_drawer_under_the_combination_cabinet" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_tienkung_xsens_1rgb":
        robot_infor = {
            "camera_names": ['camera_top'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['puppet','master'],
            "controls": ['joint_position', 'end_effector'],
            "resolution": RESOLUTION
        }
        env_name = "place_button" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_agilex_3rgb":
        robot_infor = {
            "camera_names": ['camera_front', 'camera_left_wrist', 'camera_right_wrist'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['puppet', 'master'],
            "controls":  ['end_effector_left', 'end_effector_right', 'joint_effort_left', 'joint_effort_right', 'joint_position_left', 'joint_position_right', 'joint_velocity_left', 'joint_velocity_right'],
            "resolution": RESOLUTION
        }
        env_name = "35_putcarrot" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_simulation":
        robot_infor = {
            "camera_names":  ['camera_front_external', 'camera_handeye', 'camera_left_external', 'camera_right_external'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['franka'],
            "controls": ['end_effector', 'joint_effort', 'joint_position', 'joint_velocity'],
            "resolution": RESOLUTION
        }
        env_name = "open_and_close_01" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_franka_fr3_dual":
        robot_infor = {
            "camera_names": ['camera_top', 'camera_left', 'camera_right', 'camera_front'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['puppet'],
            "controls": ['joint_position', 'end_effector'],
            "resolution": RESOLUTION
        }
        env_name = "both_pour_water" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_sim_franka_3rgb":
        robot_infor = {
            "camera_names": ['camera_front_external', 'camera_handeye', 'camera_left_external', 'camera_right_external'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['franka'],
            "controls": ['end_effector', 'joint_effort', 'joint_position', 'joint_velocity'],
            "resolution": RESOLUTION
        }
        env_name = "open_and_close_07" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_sim_tienkung_1rgb":
        robot_infor = {
            "camera_names": ['camera_chest', 'camera_head'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['tiangong'],
            "controls": ['left_arm_joint_effort_seqs', 'left_arm_joint_pos_seq', 'left_arm_joint_vel_seq', 'left_end_effector_waist', 'left_hand_joint_effort_seq', 'left_hand_joint_pos_seq', 'left_hand_joint_vel_seq',
                         'right_arm_joint_effort_seq', 'right_arm_joint_pos_seq', 'right_arm_joint_vel_seq', 'right_end_effector_waist', 'right_hand_joint_pos_seq', 'right_hand_joint_vel_seq'],
            "resolution": RESOLUTION
        }
        env_name = "pick_and_place_01_tienkung" if args.env_name is None else args.env_name
    elif args.embodiments == "h5_tienkung_prod1_gello_1rgb":
        robot_infor = {
            "camera_names": ['camera_top'],
            "camera_sensors": ['rgb_images', 'depth_images'],
            "arms": ['puppet', 'master'],
            "controls": ['joint_position'],
            "resolution": RESOLUTION
        }
        env_name = "pick_up_foil_plate_place_in_dustbin" if args.env_name is None else args.env_name
    else:
        raise ValueError(f"Invalid embodiment: {args.embodiments}")
    dataset_dir = os.path.join(args.dataset_path, args.embodiments)
    cur_embodiments = args.embodiments
    convert_dataset_image(cur_embodiments, robot_infor, resolution=RESOLUTION, dataset_dir=dataset_dir, env_names=[env_name], save_dir=args.save_dir,episode_num_pertask=1)


# Quick Start 
Set `dataset_path` to the local RoboMIND directory and specify `embodiments`, `env_name` and `save_dir`.


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # ./data
    parser.add_argument("--embodiments", type=str, 
                     choices=[
                        "h5_franka_1rgb", "h5_franka_3rgb", "h5_tienkung_gello_1rgb", "h5_tienkung_xsens_1rgb", "h5_ur_1rgb", "h5_agilex_3rgb", "h5_simulation",
                        "h5_franka_fr3_dual", "h5_sim_franka_3rgb", "h5_sim_tienkung_1rgb", "h5_tienkung_prod1_gello_1rgb"],
                     default="h5_franka_1rgb",
                     help="Choose the embodiment for data processing")
    parser.add_argument("--dataset_path", type=str, default="./data")
    parser.add_argument("--env_name", type=str, default=None)
    parser.add_argument("--save_dir", type=str, default="./save_dir",)
    args = parser.parse_args()
    main(args)

