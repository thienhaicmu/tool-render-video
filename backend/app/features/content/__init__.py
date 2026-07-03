"""Content Studio feature package (CS-A+).

Own API surface for the script-driven Content Studio. The RENDER itself runs on
the SHARED render engine via /api/render/process (render_format="content") — this
package only owns the Content-Studio-specific steps (planning now; narration
preview + asset management in later CS phases).
"""
