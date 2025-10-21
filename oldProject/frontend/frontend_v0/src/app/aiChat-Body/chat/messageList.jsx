import React, { useRef, useEffect } from "react";

const MessageList = ({ messages }) => {
    const bottomRef = useRef(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    return (
        <div className="w-full max-w-xl mx-auto flex flex-col gap-4 py-8">
            {messages.map((msg, idx) => (
                <div
                    key={idx}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                    <div
                        className={`px-4 py-2 rounded-xl max-w-[80%] break-words ${msg.role === "user"
                            ? "bg-blue-500 text-white"
                            : "bg-gray-100 text-gray-900"
                            }`}
                    >
                        {msg.content}
                        {msg.file && (
                            <div className="mt-2">
                                {msg.file.type?.startsWith("image/") ? (
                                    <img
                                        src={URL.createObjectURL(msg.file)}
                                        alt={msg.file.name}
                                        className="max-w-xs max-h-40 rounded mt-1"
                                    />
                                ) : (
                                    <a
                                        href={URL.createObjectURL(msg.file)}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-blue-600 underline break-all"
                                    >
                                        {msg.file.name}
                                    </a>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            ))}
            <div ref={bottomRef} />
        </div>
    );
};

export default MessageList;
