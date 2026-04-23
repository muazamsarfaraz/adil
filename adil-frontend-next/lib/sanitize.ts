import { defaultSchema } from "rehype-sanitize";

export const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    a: [["href", /^(?!javascript:|data:|vbscript:)/i], "title"],
  },
  protocols: {
    ...defaultSchema.protocols,
    href: ["http", "https", "mailto"],
  },
};

export function rehypeSafeLinks() {
  return (tree: any) => {
    const visit = (node: any) => {
      if (node.type === "element" && node.tagName === "a" && node.properties) {
        delete node.properties.target;
        node.properties.rel = "noopener noreferrer";
      }
      if (node.children) node.children.forEach(visit);
    };
    visit(tree);
  };
}
