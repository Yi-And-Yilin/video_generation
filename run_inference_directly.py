import logging
from argparse import ArgumentParser
from pathlib import Path
import os
import torch
import torchaudio

from mmaudio.eval_utils import (ModelConfig, all_model_cfg, generate, load_video, make_video,
                                setup_eval_logging)
from mmaudio.model.flow_matching import FlowMatching
from mmaudio.model.networks import MMAudio, get_my_mmaudio
from mmaudio.model.utils.features_utils import FeaturesUtils

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

log = logging.getLogger()

def run_inference(net, feature_utils, fm, rng, seq_cfg,
                  video_path, prompt, negative_prompt, duration, cfg_strength,
                  mask_away_clip, output_dir, output_filename, skip_video_composite):

    if video_path is not None:
        log.info(f'Using video {video_path}')
        video_info = load_video(video_path, duration)
        clip_frames = video_info.clip_frames
        sync_frames = video_info.sync_frames
        duration = video_info.duration_sec
        if mask_away_clip:
            clip_frames = None
        else:
            clip_frames = clip_frames.unsqueeze(0)
        sync_frames = sync_frames.unsqueeze(0)
    else:
        log.info('No video provided -- text-to-audio mode')
        clip_frames = sync_frames = None

    seq_cfg.duration = duration
    net.update_seq_lengths(seq_cfg.latent_seq_len, seq_cfg.clip_seq_len, seq_cfg.sync_seq_len)

    log.info(f'Prompt: {prompt}')
    log.info(f'Negative prompt: {negative_prompt}')

    audios = generate(clip_frames,
                      sync_frames, [prompt],
                      negative_text=[negative_prompt],
                      feature_utils=feature_utils,
                      net=net,
                      fm=fm,
                      rng=rng,
                      cfg_strength=cfg_strength)
    audio = audios.float().cpu()[0]
    
    if video_path is not None and not skip_video_composite:
        video_save_path = output_dir / output_filename
        make_video(video_info, video_save_path, audio, sampling_rate=seq_cfg.sampling_rate)
        log.info(f'Video saved to {video_save_path}')
    else:
        log.info('No video composite generated.')

@torch.inference_mode()
def main():
    setup_eval_logging()

    # --- Configuration ---
    variant = 'small_16k'
    weights_path = Path("D:/MMAudio/finetuned_weights/raw_caption_1000.pth")
    video_base_path = Path("D:/ComfyUI_windows_portable/ComfyUI/output/video")
    duration = 8.0
    cfg_strength = 4.5
    num_steps = 25
    seed = 42
    # ---------------------

    # --- Define your videos here ---
    videos_to_process = [
        {"code": "ybktwvn5", "positive_prompt": "woman moaning,missionary", "negative_prompt": "harsh, noise, music"},
        {"code": "vdqdulsg", "positive_prompt": "woman moaning, masturbation", "negative_prompt": "harsh, noise, music"},
    ]
    # --------------------------------

    if variant not in all_model_cfg:
        raise ValueError(f'Unknown model variant: {variant}')
    model: ModelConfig = all_model_cfg[variant]
    if not weights_path:
        model.download_if_needed()
    seq_cfg = model.seq_cfg

    device = 'cpu'
    if torch.cuda.is_available():
        device = 'cuda'
    elif torch.backends.mps.is_available():
        device = 'mps'
    else:
        log.warning('CUDA/MPS are not available, running on CPU')
    dtype = torch.bfloat16

    # load a pretrained model
    net: MMAudio = get_my_mmaudio(model.model_name).to(device, dtype).eval()
    if weights_path:
        log.info(f'Loading custom weights from {weights_path}')
        checkpoint = torch.load(weights_path, map_location=device)
        if 'weights' in checkpoint:
            weights = checkpoint['weights']
        else:
            weights = checkpoint
        net.load_weights(weights)
    else:
        log.info(f'Loaded weights from {model.model_path}')
        net.load_weights(torch.load(model.model_path, map_location=device, weights_only=True))

    # misc setup
    rng = torch.Generator(device=device)
    rng.manual_seed(seed)
    fm = FlowMatching(min_sigma=0, inference_mode='euler', num_steps=num_steps)

    feature_utils = FeaturesUtils(tod_vae_ckpt=model.vae_path,
                                  synchformer_ckpt=model.synchformer_ckpt,
                                  enable_conditions=True,
                                  mode=model.mode,
                                  bigvgan_vocoder_ckpt=model.bigvgan_16k_path,
                                  need_vae_encoder=False)
    feature_utils = feature_utils.to(device, dtype).eval()

    for video_info in videos_to_process:
        code = video_info["code"]
        positive_prompt = video_info["positive_prompt"]
        negative_prompt = video_info["negative_prompt"]
        
        video_path = video_base_path / f"{code}.mp4"
        output_filename = f"{code}.mp4"

        if not video_path.exists():
            log.warning(f"--- Warning: Video not found, skipping: {video_path} ---")
            continue

        log.info(f"--- Processing video: {video_path} ---")
        log.info(f"  Prompt: {positive_prompt}")
        log.info(f"  Negative Prompt: {negative_prompt}")

        run_inference(net, feature_utils, fm, rng, seq_cfg,
                      video_path=video_path, prompt=positive_prompt, negative_prompt=negative_prompt,
                      duration=duration, cfg_strength=cfg_strength,
                      mask_away_clip=False, output_dir=video_base_path,
                      output_filename=output_filename, skip_video_composite=False)

    log.info('--- All videos processed. ---')
    log.info('Memory usage: %.2f GB', torch.cuda.max_memory_allocated() / (2**30))


if __name__ == '__main__':
    main()
