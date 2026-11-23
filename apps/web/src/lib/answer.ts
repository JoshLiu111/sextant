// An AI answer (AI Analyst or AI Explain) as checked segments. Mirrors
// apps/compute/sextant_compute/ai/citations.py.

export type AnswerText = { type: "text"; text: string };

/** A number the model cited, checked against the calculation it names. */
export type AnswerCitation = {
  type: "citation";
  /** The number as the model wrote it. */
  text: string;
  calculation_id: string;
  metric: string;
  /** The metric's value in that calculation (null if there is none). */
  actual: number | null;
  unit: string | null;
  matches: boolean;
  /** Why it doesn't check out (null when it matches). */
  reason: string | null;
};

/** A number the model wrote without citing a calculation: nothing checked it. */
export type AnswerUncited = { type: "uncited"; text: string };

export type AnswerSegment = AnswerText | AnswerCitation | AnswerUncited;
