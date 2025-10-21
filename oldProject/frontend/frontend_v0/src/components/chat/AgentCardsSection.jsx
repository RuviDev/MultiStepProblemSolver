import React from "react";
import { AGENT } from "../../assets";

const agents = [
  { title: "Agent Analysis" },
  { title: "Agent Planning" },
  { title: "Agent verify" },
  { title: "Agent Execute" },
];

const AgentCardsSection = () => (
  <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mt-8 w-full max-w-4xl">
    {agents.map((agent, idx) => (
      <div
        key={idx}
        className="flex flex-col items-center bg-white border border-gray-200 rounded-2xl p-6 shadow-sm hover:shadow-md transition"
      >
        <div className="mb-3">
          <img
            src={AGENT}
            alt="Logo"
            className="h-10 object-contain shrink-0 select-none"
            loading="eager"
          />
        </div>
        <div className="text-base font-medium text-gray-500 text-center">
          {agent.title}
        </div>
      </div>
    ))}
  </div>
);

export default AgentCardsSection;
