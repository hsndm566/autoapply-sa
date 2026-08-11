// init-and-run.js — boots n8n, imports all workflows from /workflows, activates them.
const { spawn, execSync } = require("child_process");

// 1) start n8n server in background
const n8n = spawn("n8n", ["start"], {
  env: { ...process.env, N8N_PORT: process.env.N8N_PORT || "5678" },
  stdio: "inherit",
});

// 2) wait for server, then import + activate
function waitAndImport() {
  const attempts = 30;
  let i = 0;
  const poll = setInterval(() => {
    i++;
    try {
      // import all workflows from /workflows (each .json is a full export)
      execSync("n8n import:workflow --input=/workflows --separate", { stdio: "inherit" });
      console.log("WORKFLOWS IMPORTED");
      clearInterval(poll);
    } catch (e) {
      if (i >= attempts) {
        console.log("IMPORT FAILED after retries:", e.message);
        clearInterval(poll);
      } else {
        console.log(`n8n not ready yet (${i}/${attempts}), retrying...`);
      }
    }
  }, 5000);
}

setTimeout(waitAndImport, 15000);

n8n.on("exit", (code) => {
  console.log(`n8n exited with ${code}`);
  process.exit(code);
});
