/** Join class names, skipping falsy ones. */
export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

/** Asymmetric card shapes, cycled by index so neighbouring cards never match. */
export const CARD_SHAPES = [
  "rounded-[2rem] rounded-tl-[4rem]",
  "rounded-[2rem] rounded-br-[4rem]",
  "rounded-[2rem] rounded-tr-[5rem]",
  "rounded-[2rem]",
  "rounded-[2rem] rounded-bl-[4rem]",
  "rounded-[2rem] rounded-tl-[3rem] rounded-br-[3rem]",
];
