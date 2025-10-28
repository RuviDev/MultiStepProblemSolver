// // src/app/aiChat-Body/chat/AssistantProgress.jsx
// import React from "react";

// /**
//  * Props:
//  * - currentLabel: string
//  * - status: "running" | "done" | "error"
//  */
// export default function AssistantProgress({ currentLabel = "Thinking…", status = "running" }) {
//   return (
//     <div className="flex items-center gap-3 text-sm">
//       {status === "running" && (
//         <span className="inline-block h-4 w-4 rounded-full border-2 border-gray-300 border-t-transparent animate-spin" />
//       )}
//       {status === "done" && <span className="inline-block h-3 w-3 rounded-full bg-green-500" aria-hidden />}
//       {status === "error" && <span className="inline-block h-3 w-3 rounded-full bg-red-500" aria-hidden />}

//       <div className="flex flex-col">
//         <div className="font-medium">
//           {status === "running" ? "Thinking…" : status === "done" ? "Done" : "Something went wrong"}
//         </div>
//         <div className="text-gray-600 text-xs">{currentLabel}</div>
//       </div>
//     </div>
//   );
// }

// import Lottie from "lottie-react";
// import brainAnimation from "../../../assets/animations/brain-loading.json";

// export default function AssistantProgress({
//   currentLabel = "Thinking…",
//   status = "running",
//   size = 28 // px
// }) {
//   const isRunning = status === "running";

//   return (
//     <div className="flex items-center gap-3 text-sm" aria-live="polite">
//       {isRunning && (
//         <Lottie
//           animationData={brainAnimation}
//           loop
//           autoplay
//           style={{ width: size, height: size }}
//           className="shrink-0"
//           role="img"
//           aria-label="Thinking"
//         />
//       )}

//       {status === "done" && (
//         <span
//           className="inline-block h-3 w-3 rounded-full bg-green-500"
//           aria-hidden
//         />
//       )}

//       {status === "error" && (
//         <span
//           className="inline-block h-3 w-3 rounded-full bg-red-500"
//           aria-hidden
//         />
//       )}

//       <div className="flex flex-col">
//         <div className="font-medium">
//           {status === "running"
//             ? "Thinking…"
//             : status === "done"
//             ? "Done"
//             : "Something went wrong"}
//         </div>
//         <div className="text-gray-600 text-xs">{currentLabel}</div>
//       </div>
//     </div>
//   );
// }

import brainGif from "../../../assets/animations/brain-loading.gif";

export default function AssistantProgress({
  currentLabel = "Thinking…",
  status = "running",
}) {
  return (
    <div className="flex items-center gap-3 text-sm">
      {/* Running → brain GIF (with reduced-motion fallback) */}
      {status === "running" && (
        <>
          <img
            src={brainGif}
            alt=""                // decorative; the text below announces status
            className="h-10 w-11 rounded-sm motion-reduce:hidden"
            draggable="false"
          />
          {/* Fallback for users who prefer reduced motion */}
          <span className="hidden motion-reduce:inline text-lg leading-none" aria-hidden>
            🧠
          </span>
        </>
      )}

      {/* Done / Error dots stay the same */}
      {status === "done" && (
        <span className="inline-block h-3 w-3 rounded-full bg-green-500" aria-hidden />
      )}
      {status === "error" && (
        <span className="inline-block h-3 w-3 rounded-full bg-red-500" aria-hidden />
      )}

      {/* Live-announced status text */}
      <div className="flex flex-col" aria-live="polite" aria-atomic="true">
        <div className="font-medium">
          {status === "running"
            ? "Thinking…"
            : status === "done"
            ? "Done"
            : "Something went wrong"}
        </div>
        <div className="text-gray-600 text-xs">{currentLabel}</div>
      </div>
    </div>
  );
}
