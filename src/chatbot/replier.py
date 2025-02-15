from cltl.combot.backend.utils.casefolding import (casefold_capsule)
from cltl.reply_generation.rl_replier import RLReplier
from cltl.reply_generation.utils.replier_utils import thoughts_from_brain

from chatbot.utils.thoughts_utils import structure_correct_thought


class RLCapsuleReplier(RLReplier):
    def __init__(self, brain, savefile=None, reward=None):
        """Creates a reinforcement learning-based replier to respond to questions
        and statements by the user. Statements are replied to by phrasing a
        thought; Selection of the thoughts are learnt by the UCB algorithm.

        params
        object brain: the brain of Leolani
        str savefile: file with stored utility values in JSON format

        returns: None
        """
        super(RLCapsuleReplier, self).__init__(brain, savefile)
        self._reward_function = reward
        self._brain_stats = []
        self._log.info(f"UCB RL initialized with reward: {self._reward_function}")

    def _score_brain(self, brain_response):
        # Grab the thoughts
        thoughts = brain_response['thoughts']

        # Gather stats
        stats = {
            'turn': brain_response['statement']['turn'],
            'cardinality conflicts': len(thoughts['_complement_conflict']),
            'negation conflicts': len(thoughts['_negation_conflicts']),
            'subject gaps': len(thoughts['_subject_gaps']),
            'object gaps': len(thoughts['_complement_gaps']),
            'statement novelty': len(thoughts['_statement_novelty']),
            'subject novelty': thoughts['_entity_novelty']['_subject'],
            'object novelty': thoughts['_entity_novelty']['_complement'],
            'overlaps subject-predicate': len(thoughts['_overlaps']['_subject']),
            'overlaps predicate-object': len(thoughts['_overlaps']['_complement']),
            'trust': thoughts['_trust'],

            'Total explicit triples': len(self._brain.dataset),
            'Total classes': len(self._brain.get_classes()),
            'Total predicates': len(self._brain.get_predicates()),
            'Total semantic statements': self._brain.count_statements(),
            'Total perspectives': self._brain.count_statements(),
            'Total sources': self._brain.count_friends(),
            'Total conflicts': self._brain.get_all_negation_conflicts()
        }

        self._brain_stats.append(stats)

    def _evaluate_brain_state(self):
        brain_state = None
        # if self._reward_function == 'cardinality conflicts':
        #     len(thoughts['_complement_conflict'])

        if self._reward_function == 'Total explicit triples':
            brain_state = len(self._brain.dataset)
        elif self._reward_function == 'Total classes':
            brain_state = len(self._brain.get_classes())
        elif self._reward_function == 'Total predicates':
            brain_state = len(self._brain.get_predicates())
        elif self._reward_function == 'Total semantic statements':
            brain_state = self._brain.count_statements()
        elif self._reward_function == 'Total perspectives':
            brain_state = self._brain.count_statements()
        elif self._reward_function == 'Total sources':
            brain_state = self._brain.count_friends()
        elif self._reward_function == 'Total conflicts':
            brain_state = self._brain.get_all_negation_conflicts()

        return brain_state

    def reply_to_statement(self, brain_response, entity_only=False, proactive=True, persist=False):
        """Selects a Thought from the brain response to verbalize, and produces a template capsule for the user .

        params
        dict brain_response: brain response from brain.update() converted to JSON

        returns:
        str reply: a string representing a verbalized thought
        dicr capsule_user: template for user to respond back
        """
        # Extract thoughts from brain response
        thoughts = thoughts_from_brain(brain_response)

        # Select thought
        self._last_thought = self._thought_selector.select(thoughts.keys())
        thought_type, thought_info = thoughts[self._last_thought]
        self._log.info(f"Chosen thought type: {thought_type}")

        # Preprocess thought_info and utterance (triples)
        thought_info = {"thought": thought_info}
        thought_info = casefold_capsule(thought_info, format="natural")
        thought_info = thought_info["thought"]

        # Generate reply as capsule
        reply, capsule_user = structure_correct_thought(brain_response['statement'], thought_type, thought_info)

        # Calculate brain state
        self._score_brain(brain_response)

        return reply, capsule_user
