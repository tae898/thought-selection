from pathlib import Path

from cltl.brain.long_term_memory import LongTermMemory
from cltl.brain.utils.base_cases import statements_new_team
from cltl.brain.utils.helper_functions import brain_response_to_json
from cltl.combot.backend.api.discrete import UtteranceType
from cltl.reply_generation.rl_replier import RLReplier
from tqdm import tqdm

# Create objects
brain = LongTermMemory(address="http://localhost:7200/repositories/thought-selection",
                       log_dir=Path("logs"),
                       clear_all=True)

replier = RLReplier(brain, Path("resources/thoughts.json"))

# Recreate conversation through ingesting capsules
for capsule in tqdm(statements_new_team):
    # Add information to the brain
    print(f"\n\n---------------------------------------------------------------\n")

    # STATEMENT
    if capsule["utterance_type"] == UtteranceType.STATEMENT:
        # Update Brain -> communicate a thought
        brain_response = brain.update(capsule, reason_types=True, create_label=True)
        brain_response = brain_response_to_json(brain_response)

        replier.reward_thought()
        reply = replier.reply_to_statement(brain_response)

        print(f"\n{capsule['triple']}\n")
        print(f"{capsule['author']}: {capsule['utterance']}")
        print(f"Leolani: {reply}")
