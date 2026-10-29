/** Model → provider badge. Shared by the drawer (S6) and trace (S7). */
export function modelProvider(model: string): string {
  const name = model.toLowerCase();
  if (name.includes("wonder")) return "Meta · Muse Wonder";
  if (name.includes("spark")) {
    if (name.includes("baseten") || name.includes("open")) return "Baseten · Spark Open";
    return "Meta · Muse Spark";
  }
  if (name.includes("fireworks")) return "Fireworks";
  if (name.includes("modal")) return "Modal";
  if (name.includes("docker")) return "Docker";
  if (name.includes("stub") || name.includes("heuristic")) return "Local heuristic";
  if (!name) return "—";
  return model;
}
