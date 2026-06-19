import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFileSync } from "fs";

const server = new McpServer({
  name: "slack-poster",
  version: "1.0.0",
  description: "Posts messages and formatted briefs to Slack channels",
});

// Tool 1: Post a plain text message
server.tool(
  "post_to_slack",
  {
    message: z.string().describe("The message text to post"),
    channel: z.string().default("#daily-brief").describe("Slack channel name"),
  },
  async ({ message, channel }) => {
    const token = process.env.SLACK_BOT_TOKEN;
    if (!token) {
      return {
        content: [{ type: "text", text: "ERROR: SLACK_BOT_TOKEN not set in environment" }],
        isError: true,
      };
    }

    const res = await fetch("https://slack.com/api/chat.postMessage", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ channel, text: message }),
    });

    const data = await res.json();
    if (!data.ok) {
      return {
        content: [{ type: "text", text: `Slack API error: ${data.error}` }],
        isError: true,
      };
    }

    return {
      content: [{ type: "text", text: `Posted to ${channel} successfully.` }],
    };
  }
);

// Tool 2: Read a markdown file and post its contents to Slack
server.tool(
  "post_file_to_slack",
  {
    filepath: z.string().describe("Absolute path to the markdown file to post"),
    channel: z.string().default("#daily-brief").describe("Slack channel name"),
    header: z.string().optional().describe("Optional header line prepended to the post"),
  },
  async ({ filepath, channel, header }) => {
    const token = process.env.SLACK_BOT_TOKEN;
    if (!token) {
      return {
        content: [{ type: "text", text: "ERROR: SLACK_BOT_TOKEN not set in environment" }],
        isError: true,
      };
    }

    let content;
    try {
      content = readFileSync(filepath, "utf-8");
    } catch (err) {
      return {
        content: [{ type: "text", text: `ERROR: Could not read file at ${filepath}: ${err.message}` }],
        isError: true,
      };
    }

    const message = header ? `${header}\n\n${content}` : content;

    // Slack has a 4000 char limit per message — chunk if needed
    const chunks = [];
    for (let i = 0; i < message.length; i += 3900) {
      chunks.push(message.slice(i, i + 3900));
    }

    for (const chunk of chunks) {
      const res = await fetch("https://slack.com/api/chat.postMessage", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ channel, text: chunk }),
      });

      const data = await res.json();
      if (!data.ok) {
        return {
          content: [{ type: "text", text: `Slack API error: ${data.error}` }],
          isError: true,
        };
      }
    }

    return {
      content: [{ type: "text", text: `File posted to ${channel} (${chunks.length} message(s)).` }],
    };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
