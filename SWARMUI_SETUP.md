# SwarmUI Image Generation Setup

SEL can now generate images using SwarmUI (Stable Diffusion)!

## Requirements

1. **SwarmUI** installed and running
   - Download: https://github.com/mcmonkeyprojects/SwarmUI
   - Default runs on `http://localhost:7801`

2. **Stable Diffusion model** loaded in SwarmUI
   - Any SD 1.5, SDXL, or Flux model will work
   - Place models in SwarmUI's `Models/` directory

## Configuration

Add to your `.env` file:

```env
# SwarmUI Configuration (optional - defaults shown)
SWARMUI_URL=http://localhost:7801
SWARMUI_API_KEY=
```

## Usage

### Direct Agent Call

Use `agent:image_gen` to generate images:

```
agent:image_gen a sunset over the ocean
agent:image_gen cat wearing sunglasses in cyberpunk city
agent:image_gen abstract art with vibrant colors
```

### Natural Language

SEL can also generate images when asked naturally (if it decides to use the agent):

```
"can you generate an image of a dragon?"
"make me a picture of a cozy coffee shop"
"create an illustration of a forest at night"
```

## How It Works

1. User requests an image
2. SEL uses the `image_gen` agent
3. Agent calls SwarmUI API with the prompt
4. SwarmUI generates the image using Stable Diffusion
5. Image is saved temporarily and uploaded to Discord
6. Temp file is cleaned up after upload

## Image Settings

Default settings (configured in `agents/image_gen.py`):
- **Resolution**: 512x512
- **Steps**: 20
- **CFG Scale**: 7.0
- **Sampler**: DPM++ 2M Karras
- **Negative Prompt**: blurry, low quality, distorted, ugly, watermark

To customize, edit the `_generate_image()` function in `agents/image_gen.py`.

## Troubleshooting

**"SwarmUI not responding"**
- Make sure SwarmUI is running (`http://localhost:7801` should show the UI)
- Check `SWARMUI_URL` in `.env` matches your SwarmUI port

**"Cannot connect to SwarmUI"**
- Verify SwarmUI is started
- Check firewall isn't blocking localhost connections
- Try opening SwarmUI in browser to confirm it's working

**"Image generation failed"**
- Check SwarmUI logs for errors
- Ensure a Stable Diffusion model is loaded
- Try generating an image manually in SwarmUI first

**"Image upload failed"**
- Discord file size limit is 25MB (8MB for non-Nitro)
- Check disk space for temp files
- Verify bot has permission to attach files in the channel

## Example Output

When working, you'll see:

```
User: agent:image_gen a cute robot
SEL: [image_gen] ✨ Generated image: a cute robot
     [Image of cute robot attached]
```

## Notes

- Generation takes 5-30 seconds depending on your GPU
- SwarmUI must be running for image generation to work
- Images are temporarily saved to system temp directory
- Only authorized users (APPROVAL_USER_ID) can use agents by default
