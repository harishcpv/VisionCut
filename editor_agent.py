import ffmpeg
import imageio_ffmpeg
import os

ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

def cut_and_merge(video_path, audio_path, start_time, end_time, output_filename, vtt_path=None, hook_text="", cta_text=""):
    print(f"🎬 Processing full-length video ({start_time}s to {end_time}s) with original audio & hooks...")
    
    duration = end_time - start_time
    
    # Grab primary video and original audio streams
    input_file = ffmpeg.input(video_path, ss=start_time, t=duration)
    video = input_file.video
    original_audio = input_file.audio  # Preserves your full video's original sound!
    
    # --- ENGAGEMENT ENGINE (Dynamic Pop-up Text & Hooks) ---
    font_path = "C:/Windows/Fonts/impact.ttf"
    
    # 1. Viral Hook (Top of screen, first 3 seconds, Black Box)
    if hook_text:
        video = video.drawtext(
            text=hook_text, fontfile=font_path, fontsize=64, fontcolor='white',
            box=1, boxcolor='black@0.7', boxborderw=15,
            x='(w-text_w)/2', y='h/8', enable='between(t,0,3)'
        )
        
    # 2. Subscribe CTA (Bottom of screen, last 3 seconds, Red Box)
    if cta_text:
        cta_start = max(0, duration - 3)
        video = video.drawtext(
            text=cta_text, fontfile=font_path, fontsize=72, fontcolor='white',
            box=1, boxcolor='red@0.8', boxborderw=20,
            x='(w-text_w)/2', y='h*0.8', enable=f'between(t,{cta_start},{duration})'
        )

    try:
        # Render using the original video audio so length is 100% preserved
        stream = ffmpeg.output(
            video, 
            original_audio, 
            output_filename, 
            vcodec='libx264', 
            acodec='aac',
            pix_fmt='yuv420p'
        )
            
        ffmpeg.run(stream, cmd=ffmpeg_exe, overwrite_output=True, quiet=True)
        print("✅ Successfully rendered full-length master video!")
    except ffmpeg.Error as e:
        print("FFmpeg Error:", e.stderr.decode('utf8'))