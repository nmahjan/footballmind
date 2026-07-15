import { C } from "../../fm/theme.js";

export default function ShaderWaves({ className = "" }) {
  return (
    <div className={`shader-waves ${className}`} aria-hidden="true">
      <div
        className="shader-waves-layer shader-waves-layer-a"
        style={{ "--wave-color-a": C.home, "--wave-color-b": C.blue }}
      />
      <div
        className="shader-waves-layer shader-waves-layer-b"
        style={{ "--wave-color-a": C.blue, "--wave-color-b": C.home }}
      />
      <div
        className="shader-waves-layer shader-waves-layer-c"
        style={{ "--wave-color-a": "#8b5cf6", "--wave-color-b": C.home }}
      />
    </div>
  );
}
