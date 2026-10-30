/** Browser playback of a MediaMTX path: WebRTC (WHEP, RFC 9725) with LL-HLS as the fallback. */

export type PlaybackMode = "webrtc" | "hls";

/** A running playback: `lost` settles when the stream drops, `latency` samples it in ms. */
export type Playback = {
  lost: Promise<void>;
  latency: () => Promise<number | null>;
  stop: () => void;
};

const CONNECT_TIMEOUT_MS = 8_000;
const ICE_GATHER_TIMEOUT_MS = 1_500;

function withTimeout<T>(promise: Promise<T>, ms: number, what: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${what} timed out`)), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error instanceof Error ? error : new Error(String(error)));
      },
    );
  });
}

function iceGathered(pc: RTCPeerConnection): Promise<void> {
  return new Promise((resolve) => {
    if (pc.iceGatheringState === "complete") return resolve();
    const done = () => {
      if (pc.iceGatheringState !== "complete") return;
      pc.removeEventListener("icegatheringstatechange", done);
      resolve();
    };
    pc.addEventListener("icegatheringstatechange", done);
    // Not every candidate has to arrive: a host candidate is enough on a LAN or a tunnel.
    setTimeout(resolve, ICE_GATHER_TIMEOUT_MS);
  });
}

function connected(pc: RTCPeerConnection): Promise<void> {
  return new Promise((resolve, reject) => {
    const check = () => {
      if (pc.connectionState === "connected") resolve();
      else if (pc.connectionState === "failed" || pc.connectionState === "closed") {
        reject(new Error(`WebRTC ${pc.connectionState}`));
      } else return;
      pc.removeEventListener("connectionstatechange", check);
    };
    pc.addEventListener("connectionstatechange", check);
    check();
  });
}

/** Jitter-buffer delay plus half the round trip: what the browser adds on top of capture. */
async function webrtcLatency(pc: RTCPeerConnection): Promise<number | null> {
  let buffer: number | null = null;
  let halfRtt = 0;
  (await pc.getStats()).forEach((report: Record<string, unknown>) => {
    if (report.type === "inbound-rtp" && report.kind === "video") {
      const delay = report.jitterBufferDelay;
      const emitted = report.jitterBufferEmittedCount;
      if (typeof delay === "number" && typeof emitted === "number" && emitted > 0) {
        buffer = (delay / emitted) * 1000;
      }
    } else if (report.type === "candidate-pair" && report.nominated === true) {
      const rtt = report.currentRoundTripTime;
      if (typeof rtt === "number") halfRtt = (rtt * 1000) / 2;
    }
  });
  return buffer === null ? null : buffer + halfRtt;
}

/** Short-lived stream token (FR-SEC-007); `null` when the server does not require one. */
export type StreamToken = string | null;

export async function startWhep(
  url: string,
  video: HTMLVideoElement,
  token: StreamToken = null,
): Promise<Playback> {
  const pc = new RTCPeerConnection();
  const abort = new AbortController();
  let lose: () => void = () => {};
  const lost = new Promise<void>((resolve) => (lose = resolve));
  const stop = () => {
    abort.abort();
    pc.close();
    video.srcObject = null;
  };
  try {
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.ontrack = (event) => {
      video.srcObject = event.streams[0] ?? null;
    };
    await pc.setLocalDescription(await pc.createOffer());
    await iceGathered(pc);
    const answer = await withTimeout(
      fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/sdp",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: pc.localDescription?.sdp,
        signal: abort.signal,
      }),
      CONNECT_TIMEOUT_MS,
      "WHEP request",
    );
    if (answer.status !== 201) throw new Error(`WHEP answered HTTP ${answer.status}`);
    await pc.setRemoteDescription({ type: "answer", sdp: await answer.text() });
    await withTimeout(connected(pc), CONNECT_TIMEOUT_MS, "WebRTC connection");
  } catch (error) {
    stop();
    throw error;
  }
  pc.addEventListener("connectionstatechange", () => {
    if (pc.connectionState === "failed" || pc.connectionState === "closed") lose();
  });
  return { lost, latency: () => webrtcLatency(pc), stop };
}

export async function startHls(
  url: string,
  video: HTMLVideoElement,
  token: StreamToken = null,
): Promise<Playback> {
  let lose: () => void = () => {};
  const lost = new Promise<void>((resolve) => (lose = resolve));

  // Native HLS cannot add an Authorization header, so a token forces hls.js.
  if (!token && video.canPlayType("application/vnd.apple.mpegurl")) {
    // Safari plays HLS natively.
    video.src = url;
    const stop = () => {
      video.removeAttribute("src");
      video.load();
    };
    video.addEventListener("error", () => lose(), { once: true });
    try {
      await withTimeout(video.play(), CONNECT_TIMEOUT_MS, "HLS playback");
    } catch (error) {
      stop();
      throw error;
    }
    return { lost, latency: () => Promise.resolve(null), stop };
  }

  const { default: Hls } = await import("hls.js");
  if (!Hls.isSupported()) throw new Error("HLS is not supported by this browser");
  const hls = new Hls({
    lowLatencyMode: true,
    xhrSetup: (xhr) => {
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    },
  });
  const stop = () => {
    hls.destroy();
    video.removeAttribute("src");
  };
  try {
    await withTimeout(
      new Promise<void>((resolve, reject) => {
        hls.on(Hls.Events.ERROR, (_event, data) => {
          if (!data.fatal) return;
          reject(new Error(`HLS ${data.details}`));
          lose();
        });
        video.addEventListener("playing", () => resolve(), { once: true });
        hls.loadSource(url);
        hls.attachMedia(video);
        void video.play().catch(() => {});
      }),
      CONNECT_TIMEOUT_MS,
      "HLS playback",
    );
  } catch (error) {
    stop();
    throw error;
  }
  return { lost, latency: () => Promise.resolve(hls.latency ? hls.latency * 1000 : null), stop };
}
