export type ResultStatus = "applies" | "unknown" | "superseded" | "not_yet_effective" | "pending";

export type Category =
  | "rent_increase_limits"
  | "just_cause_eviction"
  | "security_deposits"
  | "application_screening_fees"
  | "screening_restrictions"
  | "algorithmic_rent_setting";

export interface RuleInfo {
  title: string;
  jurisdiction: string;
  level: "state" | "city";
  category: Category;
  requirement: string;
  key_value: string | null;
  citation: string;
  quoted_span: string;
  quote_offsets: Record<string, [number, number]> | null;
  source_doc_id: string;
  member_docs: string[] | null;
  effective_date: string | null;
  effective_date_span: string | null;
  confidence: number | null;
  conflict_note: string | null;
  secondary_source: boolean | null;
  instrument: string | null;
  enacted: boolean | null;
  interaction: string | null;
}

export interface Result {
  team_rule_id: string;
  result: ResultStatus;
  explanation: string;
  conflict_flag: boolean;
  missing_facts: string[];
  rule: RuleInfo;
}

export interface Stack {
  state: string;
  county: string | null;
  city: string | null;
  method: string | null;
  confidence: number;
  matched: string | null;
  note: string | null;
  lon?: number;
  lat?: number;
}

export interface Facts {
  year_built: number | null;
  units: number | null;
  units_min: number | null;
  units_max: number | null;
  use_description: string | null;
  subsidized: boolean | null;
  owner_occupied?: boolean | null;
  missing: string[];
  derived: string[];
  notes: string[];
  user_supplied?: string[];
}

export interface Lookup {
  address_id: string | null;
  as_of: string;
  address: { street_address: string; postal_city: string; state: string; zip: string };
  stack: Stack;
  facts: Facts;
  results: Result[];
  kb_version: number;
  disclaimer: string;
}

export interface AddressHit {
  address_id: string;
  label: string;
  legal_city: string | null;
}

export interface LibraryRule {
  team_rule_id: string;
  jurisdiction: string;
  level: string;
  category: Category;
  title: string;
  requirement: string;
  key_value: string | null;
  citation: string;
  effective_date: string | null;
  enacted: boolean;
  failed: boolean;
  status: string;
  confidence: number | null;
  conflict_flag: boolean;
  conflict_note: string | null;
  source_doc_id: string;
  quoted_span: string;
  quote_offsets: Record<string, [number, number]> | null;
  secondary_source: boolean | null;
}

export interface SourceExcerpt {
  doc_id: string;
  url: string;
  retrieved_at: string | null;
  source_type: string;
  in_corpus: boolean;
  before?: string;
  quote?: string;
  after?: string;
}

export interface Resource {
  doc_id: string;
  url: string;
  jurisdiction: string;
  title: string;
  host: string;
}

/** Facts the person can confirm; sent to the same deterministic evaluator. */
export interface FactsInput {
  year_built?: number | null;
  units?: number | null;
  subsidized?: boolean | null;
  owner_occupied?: boolean | null;
}

export interface CustomAddress {
  street: string;
  city: string;
  state: string;
  zip: string;
}

/** A report target: a sample address id or a custom address. */
export type Target = { kind: "sample"; id: string } | { kind: "custom"; address: CustomAddress };
