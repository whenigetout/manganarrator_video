# Audio Studio: Quick Reference

## Start

1. Double-click **Launch Studio.cmd** in the repo.
2. Keep the launcher window open. It opens the React studio in your browser.
3. To reopen/unlock publishing later, double-click the launcher again. It reuses its running server.

The existing Conda backend environment, FFmpeg/FFprobe, and Node.js are prerequisites. No Conda activation or curl is needed for normal use. See [setup](PUBLISHING_GUIDE.md) for a new machine.

## One-Time YouTube Setup

1. Open **Channel profiles and setup** (settings icon beside YouTube publishing).
2. Import your Google OAuth **Web application** client JSON. Register the exact redirect URI displayed in the dialog in Google Cloud.
3. Under **Metadata providers**, enter your provider URL, model and API key. Save.
4. Enter a profile name, select its metadata provider, and set metadata style/tags/privacy. Save the profile.
5. **Connect YouTube**, choose the correct Google account/channel, and approve access. Return to the studio.
6. Tune the visualizer once; **Save current visual settings** in that profile.
7. Repeat profile creation/connection for every independent channel.

## Every Recording

1. Choose **Audio file**: MP3 or WAV (also FLAC, M4A, OGG and AAC).
2. Choose the **Channel profile**. Its saved visual settings load automatically.
3. Optionally add song/performer/recording facts under **Recording context / transcript**. Without facts, metadata stays conservative; the app does not recognize songs or invent credits.
4. Press **Prepare for YouTube**. Rendering and metadata generation run automatically.
5. Review the video, title, description, tags, channel, privacy, kids setting and altered/synthetic-content setting.
6. Tick the review checkbox and press **Approve & upload**.
7. Follow publishing progress. The YouTube ID/link appears after upload; the job completes after YouTube processing.

Private is the default. Unlisted is available. Public requires a separate explicit confirmation on that upload. The app does not bypass YouTube's API-project restrictions.

## Useful Editor Controls

| Want to... | Control |
|---|---|
| Start with a ring, corner ring, bottom bars, or both | Spectrum -> Composition preset -> Apply |
| Inspect just the background | Background only above the live editor; export is unchanged |
| Preview background changes | Background tab + Frame time; uses the export compositor |
| Use a video background | Background -> media -> upload clips; reorder with arrows |
| Keep proportions when changing 1080p/2K/4K | Export -> Scale layers with resolution |
| Emphasize bass or a frequency range | Minimum/Maximum frequency, Sensitivity and Response scale |
| Improve contrast behind a spectrum | Backdrop opacity |
| Undo an experiment | Undo/redo icons above the live editor |
| Check framing or download a still | Framing guides / download icon; guides are not exported |
| Watch an encoded test | Preview 5 seconds -> Rendered video |
| Generate only a local MP4 | Render video; no Google or LLM setup required |

## Where Are My Files?

- Videos: `<media_root>/outputs/audio_video/publish_<run-id>/<output-name>.mp4` for publishing runs.
- Use the **Download** links; the output remains local even if YouTube upload fails.
- Publishing history/configuration: `%LOCALAPPDATA%/MangaNarrator/publishing/`.
- Tokens/API keys: Windows Credential Manager via `keyring`, not Git or the browser.

## Something Failed?

- **Metadata failure:** edit the draft manually, or fix provider settings and regenerate metadata.
- **Channel authorization expired:** reconnect the same profile, then retry the failed stage.
- **Network interruption:** upload retries automatically, using YouTube's confirmed byte offset.
- **Session expired / completion uncertain:** check YouTube Studio before explicitly restarting. Never assume a missing response means no upload happened.
- **Still private:** check the Google API project audit restriction, not just the requested privacy setting.
- **Publishing locked:** reopen with Launch Studio.cmd. Local browser sessions last 12 hours.

Full details: [Publishing guide](PUBLISHING_GUIDE.md).
