// Timeline view moved to ./timeline/ (Gantt engine + calendar mode + shell).
// This shim keeps the router's `import("./views/timeline")` path stable.
export { default } from "./timeline/index";
