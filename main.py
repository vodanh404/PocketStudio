# ============================================================
# PocketStudio - Image Generation & Editing Script
# Chạy trong Google Colab
# ============================================================

import os
import random
import torch
import gradio as gr
from diffusers import StableDiffusionXLPipeline
from diffusers.utils import logging as diffusers_logging

diffusers_logging.set_verbosity_error()

print(">>> [1/2] Đang tải mô hình SDXL Pipeline...")

BASE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
dtype = torch.float16 if torch.cuda.is_available() else torch.float32

pipe = StableDiffusionXLPipeline.from_pretrained(
    BASE_MODEL,
    torch_dtype=dtype,
    use_safetensors=True,
    variant="fp16"
)

# Tối ưu VRAM trên Colab
pipe.enable_model_cpu_offload()
pipe.vae.enable_tiling()
pipe.vae.enable_slicing()

print(">>> PocketStudio đã sẵn sàng!")

# ---------- Giao diện Gradio: PocketStudio ----------
print(">>> [2/2] Khởi chạy giao diện PocketStudio...")

# Biến toàn cục lưu trữ ảnh và prompt trước đó để phục vụ tính năng vẽ tiếp (ghi nhớ ảnh trước)
last_generated_image = None
last_prompt = ""

def pocket_studio_generate(
    prompt: str,
    negative_prompt: str = "",
    num_inference_steps: int = 28,
    guidance_scale: float = 3.5,
    width: int = 1024,
    height: int = 1024,
    seed: int = -1,
    is_edit_mode: bool = False,
):
    global last_generated_image, last_prompt

    if not prompt or not prompt.strip():
        raise gr.Error("Prompt không được để trống")

    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    generator = torch.Generator(device="cpu").manual_seed(seed)

    # Nếu người dùng chọn chế độ vẽ tiếp/sửa ảnh trước và có ảnh trước đó
    if is_edit_mode and last_generated_image is not None:
        # Kết hợp prompt mới với prompt cũ để giữ ngữ cảnh (ghi nhớ ảnh trước)
        combined_prompt = f"{last_prompt}, {prompt}" if last_prompt else prompt
        print(f">>> Đang vẽ tiếp dựa trên ảnh trước. Prompt kết hợp: {combined_prompt}")
    else:
        combined_prompt = prompt

    try:
        result = pipe(
            prompt=combined_prompt,
            negative_prompt=negative_prompt if negative_prompt.strip() else None,
            num_inference_steps=int(num_inference_steps),
            guidance_scale=float(guidance_scale),
            width=int(width),
            height=int(height),
            generator=generator,
            max_sequence_length=512,
        )
        image = result.images[0]
        
        # Lưu lại trạng thái hiện tại để phục vụ cho lần vẽ tiếp theo
        last_generated_image = image
        last_prompt = combined_prompt

        return image, f"Seed: {seed} | Prompt thực tế: {combined_prompt}"
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        raise gr.Error("OOM – hãy giảm độ phân giải hoặc số bước (steps)")
    except Exception as e:
        raise gr.Error(f"Lỗi sinh ảnh: {str(e)}")

with gr.Blocks() as demo:
    gr.Markdown("# 🎨 PocketStudio")
    
    # Thông báo miễn trừ trách nhiệm được làm nổi bật
    gr.Markdown(
        """
        <div style="background-color: #fff3cd; color: #856404; padding: 12px 16px; border-radius: 8px; border-left: 5px solid #ffeeba; margin-bottom: 15px; font-size: 14px;">
            <strong>⚠️ MIỄN TRỪ TRÁCH NHIỆM:</strong> Các hình ảnh được tạo ra hoàn toàn tự động bằng trí tuệ nhân tạo (AI) thông qua mô hình Stable Diffusion XL. 
            Người dùng chịu hoàn toàn trách nhiệm cá nhân đối với mọi nội dung hình ảnh do mình tạo ra và sử dụng. 
            Hệ thống không chịu trách nhiệm pháp lý đối với bất kỳ hành vi lạm dụng, vi phạm bản quyền hoặc phát tán nội dung sai lệch từ phía người dùng.
        </div>
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            prompt_input = gr.Textbox(label="Prompt", lines=3, placeholder="Nhập mô tả bức ảnh bạn muốn tạo...")
            negative_prompt_input = gr.Textbox(label="Negative Prompt (tùy chọn)", lines=2, placeholder="Những gì không muốn xuất hiện...")
            
            with gr.Row():
                steps_slider = gr.Slider(4, 50, value=28, step=1, label="Inference Steps")
                guidance_slider = gr.Slider(1.0, 10.0, value=3.5, step=0.5, label="Guidance Scale")
            
            with gr.Row():
                width_drop = gr.Dropdown([512, 768, 1024], value=1024, label="Width")
                height_drop = gr.Dropdown([512, 768, 1024], value=1024, label="Height")
            
            seed_number = gr.Number(value=-1, label="Seed (-1 = random)", precision=0)
            edit_mode_checkbox = gr.Checkbox(label="Vẽ tiếp dựa trên ảnh/prompt trước đó", value=False)
            
            generate_btn = gr.Button("Tạo / Vẽ tiếp ảnh", variant="primary")

        with gr.Column(scale=1):
            output_image = gr.Image(type="pil", label="Kết quả")
            output_info = gr.Textbox(label="Thông tin chi tiết")

    generate_btn.click(
        fn=pocket_studio_generate,
        inputs=[
            prompt_input,
            negative_prompt_input,
            steps_slider,
            guidance_slider,
            width_drop,
            height_drop,
            seed_number,
            edit_mode_checkbox,
        ],
        outputs=[output_image, output_info]
    )

demo.queue(max_size=4).launch(share=True, inline=False, debug=False)
