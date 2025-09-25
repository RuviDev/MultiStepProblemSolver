import React, { useState, useRef } from "react";
import { Mic, Plus, Loader2 } from "lucide-react";

const AskField = ({ onSend }) => {
  const [askType, setAskType] = useState("ask");
  const [value, setValue] = useState("");
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [uploading, setUploading] = useState(false);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  // const handleKeyDown = (e) => {
  //   if (e.key === "Enter" && !e.shiftKey) {
  //     e.preventDefault();
  //     if (askType === "ask" && value.trim()) {
  //       onSend?.({ text: value, file: null });
  //       setValue("");
  //     } else if (askType === "upload" && (value.trim() || file)) {
  //       handleSend();
  //     }
  //   }
  // };

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    setFile(f);
    if (f && f.type.startsWith("image/")) {
      setPreviewUrl(URL.createObjectURL(f));
    } else {
      setPreviewUrl(null);
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleRemoveFile = () => {
    setFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // const handleSend = () => {
  //   if (askType === "ask") {
  //     if (value.trim()) {
  //       onSend?.({ text: value, file: null });
  //       setValue("");
  //     }
  //   } else if (askType === "upload") {
  //     if (value.trim() || file) {
  //       setUploading(true);
  //       // Simulate upload delay
  //       setTimeout(() => {
  //         setUploading(false);
  //         onSend?.({ text: value, file });
  //         setValue("");
  //         setFile(null);
  //         setPreviewUrl(null);
  //         if (fileInputRef.current) fileInputRef.current.value = "";
  //       }, 1200);
  //     }
  //   }
  // };

  const handleSend = () => {
    const text = value.trim();
    if (!text) return;
    onSend?.({ text });
    setValue("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow border border-gray-100 px-6 py-4 flex flex-col items-stretch relative">
      {/* Loading overlay */}
      {uploading && (
        <div className="absolute inset-0 bg-white/70 flex items-center justify-center z-10 rounded-2xl">
          <Loader2 className="animate-spin w-8 h-8 text-blue-500" />
        </div>
      )}
      <div
        className={`flex items-center ${
          uploading ? "pointer-events-none opacity-60" : ""
        }`}
      >
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="+ Ask relativity"
          className="flex-1 bg-transparent outline-none text-lg placeholder-gray-400 py-2 resize-none"
          style={{ minWidth: 0, maxHeight: 120 }}
          disabled={uploading}
        />
        <button
          className="ml-2 p-2 rounded-full hover:bg-gray-100 transition"
          aria-label="Mic"
          type="button"
          disabled={uploading}
        >
          <Mic className="w-6 h-6 text-gray-400" />
        </button>
        {askType === "upload" && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={handleFileChange}
              accept="image/*,application/pdf"
              disabled={uploading}
            />
            <button
              type="button"
              onClick={handleUploadClick}
              className="ml-2 p-2 rounded-full bg-gray-100 hover:bg-gray-200 transition flex items-center justify-center"
              aria-label="Upload"
              disabled={uploading}
            >
              <Plus className="w-5 h-5 text-gray-700" />
            </button>
          </>
        )}
      </div>
      {/* Media preview */}
      {askType === "upload" && file && (
        <div className="flex items-center mt-3">
          {previewUrl ? (
            <img
              src={previewUrl}
              alt={file.name}
              className="max-h-24 max-w-xs rounded border mr-3"
            />
          ) : (
            <span className="px-3 py-1 bg-gray-100 rounded text-sm text-gray-700 mr-3">
              {file.name}
            </span>
          )}
          <button
            type="button"
            onClick={handleRemoveFile}
            className="text-xs text-red-500 hover:underline"
            disabled={uploading}
          >
            Remove
          </button>
        </div>
      )}
      {/* Switch Button */}
      <div className="flex mt-4">
        <div className="flex bg-gray-100 rounded-xl p-1 w-fit">
          <button
            type="button"
            onClick={() => setAskType("ask")}
            className={`px-4 py-1.5 rounded-xl text-sm font-medium transition
              ${
                askType === "ask"
                  ? "bg-white text-gray-900 font-semibold shadow"
                  : "bg-transparent text-gray-800 hover:text-gray-900"
              }`}
            style={{ minWidth: 90 }}
            disabled={uploading}
          >
            Ask
          </button>
          <button
            type="button"
            onClick={() => setAskType("upload")}
            className={`px-4 py-1.5 rounded-xl text-sm font-medium transition
              ${
                askType === "upload"
                  ? "bg-white text-gray-900 font-semibold shadow"
                  : "bg-transparent text-gray-800 hover:text-gray-900"
              }`}
            style={{ minWidth: 120 }}
            disabled={uploading}
          >
            Upload &amp; Ask
          </button>
        </div>
      </div>
    </div>
  );
};

export default AskField;
