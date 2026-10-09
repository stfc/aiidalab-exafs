import React, { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

import AiidaExplorer from "./AiidaExplorer";
import "./index.css";

// Same-origin default: Jupyter's authenticated proxy in front of `verdi restapi`.
const DEFAULT_REST_URL = `${window.location.origin}/exafs-restapi/api/v4`;

// Full-page explorer configured by ?api_url=<REST API v4 URL>&uuid=<node uuid>.
// Replaces upstream's demo App.jsx at image build time (see docker/base/Dockerfile).
export default function App() {
  const [sp, setSp] = useSearchParams();
  const apiUrl = sp.get("api_url") ?? DEFAULT_REST_URL;
  const uuid = sp.get("uuid") ?? "";

  const handleRootNodeChange = useCallback(
    (next) => {
      const params = new URLSearchParams(sp);
      if (next) params.set("uuid", next);
      else params.delete("uuid");
      setSp(params, { replace: true });
    },
    [sp, setSp],
  );

  return (
    <div style={{ width: "100vw", height: "100vh" }}>
      <AiidaExplorer
        restApiUrl={apiUrl}
        rootNode={uuid}
        onRootNodeChange={handleRootNodeChange}
      />
    </div>
  );
}
