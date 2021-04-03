
"""
Author: lzhbrian (https://lzhbrian.me)
Date: 2020.1.20
Note: mainly modified from: https://github.com/tkarras/progressive_growing_of_gans/blob/master/util_scripts.py#L50

Modified by limgan for argparse

"""

import numpy as np
from PIL import Image
import os
import scipy
import pickle
import moviepy
import dnnlib
import dnnlib.tflib as tflib
from tqdm import tqdm
import argparse
import re
import moviepy.editor # pip install moviepy


tflib.init_tf()

def create_image_grid(images, grid_size=None):
    assert images.ndim == 3 or images.ndim == 4
    num, img_w, img_h = images.shape[0], images.shape[-1], images.shape[-2]

    if grid_size is not None:
        grid_w, grid_h = tuple(grid_size)
    else:
        grid_w = max(int(np.ceil(np.sqrt(num))), 1)
        grid_h = max((num - 1) // grid_w + 1, 1)

    grid = np.zeros(list(images.shape[1:-2]) + [grid_h * img_h, grid_w * img_w], dtype=images.dtype)
    for idx in range(num):
        x = (idx % grid_w) * img_w
        y = (idx // grid_w) * img_h
        grid[..., y : y + img_h, x : x + img_w] = images[idx]
    return grid

def generate_interpolation_video(_G,_D,Gs, truncation_psi=0.5,
                                 grid_size=[1,1], image_shrink=1, image_zoom=1, 
                                 duration_sec=60.0, smoothing_sec=1.0, 
                                 mp4='test-lerp.mp4', mp4_fps=30, 
                                 mp4_codec='libx264', mp4_bitrate='16M', 
                                 random_seed=1000):
    fmt = dict(func=tflib.convert_images_to_uint8, nchw_to_nhwc=True)
    num_frames = int(np.rint(duration_sec * mp4_fps))
    random_state = np.random.RandomState(random_seed)

    print('Generating latent vectors...')
    shape = [num_frames, np.prod(grid_size)] + Gs.input_shape[1:] # [frame, image, channel, component]
    all_latents = random_state.randn(*shape).astype(np.float32)
    all_latents = scipy.ndimage.gaussian_filter(all_latents, [smoothing_sec * mp4_fps] + [0] * len(Gs.input_shape), mode='wrap')
    all_latents /= np.sqrt(np.mean(np.square(all_latents)))

    # Frame generation func for moviepy.
    def make_frame(t):
        frame_idx = int(np.clip(np.round(t * mp4_fps), 0, num_frames - 1))
        latents = all_latents[frame_idx]
        labels = np.zeros([latents.shape[0], 0], np.float32)        
        images = Gs.run(latents, None, truncation_psi=truncation_psi, randomize_noise=False, output_transform=fmt)
        
        images = images.transpose(0, 3, 1, 2) #NHWC -> NCHW
        grid = create_image_grid(images, grid_size).transpose(1, 2, 0) # HWC
        if image_zoom > 1:
            grid = scipy.ndimage.zoom(grid, [image_zoom, image_zoom, 1], order=0)
        if grid.shape[2] == 1:
            grid = grid.repeat(3, 2) # grayscale => RGB
        return grid

    # Generate video.
    
    c = moviepy.editor.VideoClip(make_frame, duration=duration_sec)
    c.write_videofile(mp4, fps=mp4_fps, codec=mp4_codec, bitrate=mp4_bitrate)
    return c



def _str_to_bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    if v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    raise argparse.ArgumentTypeError('Boolean value expected.')

_examples = '''examples:
  python %(prog)s --outdir=out --target=targetimg.png \\
      --network=https://nvlabs-fi-cdn.nvidia.com/stylegan2-ada/pretrained/ffhq.pkl
'''


def _parse_num_range(s):
    '''Accept either a comma separated list of numbers 'a,b,c' or a range 'a-c' and return as a list of ints.'''

    range_re = re.compile(r'^(\d+)-(\d+)$')
    m = range_re.match(s)
    if m:
        return list(range(int(m.group(1)), int(m.group(2))+1))
    vals = s.split(',')
    return [int(x) for x in vals]

def generate_interp(network_pkl, seed, truncation_psi, outdir, duration=60.0, smoothing= 1.0, name='interp', fps =30):
    
    tflib.init_tf()
    print('Loading networks from "%s"...' % network_pkl)
    with dnnlib.util.open_url(network_pkl) as fp:
        _G, _D, Gs = pickle.load(fp)

    os.makedirs(outdir, exist_ok=True)
    
    seeds = _parse_num_range(seed)
    
    
    
    
    for seed in seeds:
        tmpname = (outdir + name + '_' + seed + '.mp4')
        generate_interpolation_video(_G,_D,Gs,       truncation_pis=truncation_psi, grid_size=[1,1],   
                                     duration_sec=duration, smoothing_sec=smoothing, 
                                     mp4=tmpname, mp4_fps=fps, 
                                     mp4_codec='libx264', mp4_bitrate='16M', 
                                     random_seed=seed)
    return 1
    



def main():
    parser = argparse.ArgumentParser(
        description='Project given image to the latent space of pretrained network pickle.',
        epilog=_examples,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--network', help='Network pickle filename', dest='network_pkl', required=True)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--seeds', type=_parse_num_range, help='List of random seeds')
    #g.add_argument('--dlatents', dest='dlatents_npz', help='Generate images for saved dlatents')
    parser.add_argument('--trunc', dest='truncation_psi', type=float, help='Truncation psi (default: %(default)s)', default=0.5)
   #parser.add_argument('--class', dest='class_idx', type=int, help='Class label (default: unconditional)')
    parser.add_argument('--outdir', help='Where to save the output images', required=True, metavar='DIR')
    parser.add_argument('--smoothing', help='Amount of smoothing on mp4 interframes')
    parser.add_argument('--duration', help='how long to generate interpolation for')
    parser.add_argument('--name', help='name of the mp4 file')
    parser.add_argument('--fps', help='fps of the mp4!')
    
    
    generate_interp(**vars(parser.parse_args()))



if __name__ == "__main__":
    main()
