Scrambled Echo: a VST3 delay whose echo taps are OTOC maps measured on Moth Atlas (`otoc-echo-v1`). Stereo effect, category Fx | Delay. Details: [plugin/README.md](https://github.com/SplendidAfternoon/scrambled/tree/main/plugin).

**2.1.0:** wider egg nodes. Dragging a node outward now takes its echoes all the way to the stereo edge and up to double the delay, for centre sites as well as edge sites; dragging down goes to mute and up to +12 dB. Automation recorded with 2.0 maps onto the new ranges, so re-record node drags made in 2.0. The wet signal is soft-limited above full scale, so pushing every node to +12 dB stays listenable; a stray NaN from another plugin no longer silences the echo; custom maps over 1024 cells are refused with a message in the editor.

**Windows (x64):** unzip `ScrambledEcho-*-win64-vst3.zip` and copy the `ScrambledEcho.vst3` folder into `C:\Program Files\Common Files\VST3\`, then rescan plugins in your DAW.

**macOS (Intel and Apple Silicon, 10.15+):** unzip `ScrambledEcho-macos-universal-vst3.zip` and copy `ScrambledEcho.vst3` into `~/Library/Audio/Plug-Ins/VST3/`. The build is ad-hoc signed, not notarised, so clear the download quarantine once in Terminal before rescanning:

```
xattr -dr com.apple.quarantine ~/Library/Audio/Plug-Ins/VST3/ScrambledEcho.vst3
```

The macOS build is made by GitHub Actions from the same source ([workflow](https://github.com/SplendidAfternoon/scrambled/blob/main/.github/workflows/vst.yml)); it was not tested on a Mac by hand.
