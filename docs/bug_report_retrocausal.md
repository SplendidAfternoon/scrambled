**retrocausal-echo-v1: every job ends in engine_timeout**

Hi! Every retrocausal-echo-v1 job I've submitted since Sat 3 Oct has failed with `engine_timeout` ("The engine did not respond in time — retry the job"). Other engines (otoc-echo-v1, blur-v1, telablur-v1, blur-core-v1, entanglement-shader-v1) work fine on the same key.

Job ids:
- `bc6516c5-c5c5-430d-a66a-fa2785a8ceb4`: `ir` = an otoc-echo-v1 trajectory JSON, 26.6 s audio. Stuck at "Rendering 26.6s through 348 taps", then timed out.
- `c4eefe4b-402a-4da8-8f54-259114c39e3f`: same setup. Stuck at "Building the tap map", then timed out.
- `6dabddfc-5ba3-4281-be12-c1d8e1303b72`: engine_timeout.
- A 5 s test clip also failed straight away with engine_timeout.
- `5618ae22…` and `aa558cac…` (measure step, no `ir`) sat at "waiting on aer" for over an hour.

Params: `decay=1.0, master_ms=6400, negative_mode=invert, mix=0.6, min_level=0.02, include_tap_map=true, emit=audio`.

Two other engines are timing out the same way today (4 Oct):
- tomography-api-v2: every job ends in engine_timeout after about 70 s, even a 2-qubit Bell circuit (`c34dd701-036a-4d97-86c0-a635ce346aa4`, `9a8c08d2-2889-4653-a8bc-945532b1940e`).
- tessa-image-v1: a 32 px probe timed out (`4a42a6fd-bc5d-4897-ad5d-be33bbd173ea`).

Is the engine down, or is there a size/length limit I should stay under? Thanks!
