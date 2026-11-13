import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
// A file dropped outside a drop area would make the browser leave the app to open it.
for (const type of ["dragover", "drop"])
  addEventListener(type, (e) => {
    if ((e as DragEvent).dataTransfer?.types.includes("Files")) e.preventDefault();
  });
createRoot(document.getElementById("root")!).render(<App />);
