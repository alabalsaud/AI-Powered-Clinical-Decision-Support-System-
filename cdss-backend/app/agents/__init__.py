"""
app/agents — 5-agent clinical decision pipeline.

Pipeline order:
  1. TriageAgent       — symptom extraction, urgency scoring
  2. DiagnosisAgent    — LLM differential diagnosis
  3. VerificationAgent — rule-based confirmation + confidence re-scoring
  4. MedicationAgent   — evidence-based drug suggestions + safety gate
  5. QAAgent           — accuracy scoring + audit logging
"""
