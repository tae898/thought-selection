""" Filename:     chatbots.py
    Author(s):    Thomas Bellucci
    Description:  Implementation of the Chatbot based on a Leolani backend.
                  The implementation uses the knowledge extraction modules
                  of Leolani for parsing, the Brain for storage/querying
                  of triples and modified LenkaRepliers for phrasing.                   
    Date created: Nov. 11th, 2021
"""

# Set up Java PATH (required for Windows)
import os

os.environ["JAVAHOME"] = "C:/Program Files/Java/jre1.8.0_311/bin/java.exe"

from pathlib import Path
from random import choice

# Pip-installed ctl repositories
from cltl.brain.long_term_memory import LongTermMemory
from cltl.brain.utils.helper_functions import brain_response_to_json
from cltl.combot.backend.api.discrete import UtteranceType
from cltl.combot.backend.utils.casefolding import casefold_capsule
from cltl.reply_generation.data.sentences import (GOODBYE, GREETING, SORRY, TALK_TO_ME)
from cltl.reply_generation.lenka_replier import LenkaReplier
from cltl.reply_generation.nsp_replier import NSPReplier
from cltl.reply_generation.rl_replier import RLReplier
from cltl.reply_generation.utils.replier_utils import thoughts_from_brain

from src.chatbot.utils.chatbot_utils import capsule_for_query
from src.chatbot.utils.thoughts_utils import structure_correct_thought, copy_capsule_context, BASE_CAPSULE


class Chatbot:
    def __init__(self, chat_id, speaker, mode, savefile=None):
        """Sets up a Chatbot with a Leolani backend.

        params
        str speaker:  name of speaker
        str mode:     method used to select thoughts: ['Lenka', 'RL', 'NSP']
        str savefile: path to NSP model or utilities file needed by the replier.

        returns: None
        """
        # Set up Leolani backend modules
        self.__address = "http://localhost:7200/repositories/sandbox"
        self.__brain = LongTermMemory(address=self.__address, log_dir=Path("./../../logs"), clear_all=False)
        self.__brain_stats = []

        self.__mode = mode
        self.__savefile = savefile
        self._chat_id = chat_id
        self._speaker = speaker
        self._turns = 0

        if mode == "RL":
            self.__replier = RLReplier(self.__brain, Path(savefile))
        elif mode == "NSP":
            self.__replier = NSPReplier(Path(savefile))
        elif mode == "Lenka":
            self.__replier = LenkaReplier()
        else:
            raise Exception("unknown replier mode %s (choose RL, NSP or Lenka)" % mode)

    def close(self):
        """Ends interaction and writes all learnt thought utility files
        (if method='RL') .

        returns: None
        """
        # Writes (optionally) a utilities JSON to disk
        if self.__savefile and self.__mode == "RL":
            self.__replier._RLReplier__thought_selector.save(self.__savefile)

    @property
    def replier(self):
        """Provides access to the replier."""
        return self.__replier

    @property
    def greet(self):
        """Generates a random greeting."""
        string = choice(GREETING) + " " + choice(TALK_TO_ME)

        return string

    @property
    def farewell(self):
        """Generates a random farewell message."""
        string = choice(GOODBYE)
        return string

    def _select_rl_thought(self, brain_response):
        """Takes an input brain_response and returns a capsule with which the user should interact.

        params
        BasicReplier replier: replier with thought selector included
        str brain_response:  brain_response brain_response as json

        returns:  capsule dict with utterance and context
        """
        # Extract thoughts from brain response
        thoughts = thoughts_from_brain(brain_response)

        # Select thought
        self.replier._RLReplier__last_thought = self.replier._RLReplier__thought_selector.select(thoughts.keys())
        thought_type, thought_info = thoughts[self.replier._RLReplier__last_thought]
        self.replier._log.info(f"Chosen thought type: {thought_type}")

        # Preprocess thought_info and utterance (triples)
        thought_info = {"thought": thought_info}
        thought_info = casefold_capsule(thought_info, format="natural")
        thought_info = thought_info["thought"]

        # Generate reply as capsule
        reply, capsule_user = structure_correct_thought(brain_response['statement'], thought_type, thought_info)

        return reply, capsule_user

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
            'overlaps on predicate-object': len(thoughts['_overlaps']['_complement']),
            'trust': thoughts['_trust'],

            'Total explicit triples': len(self.__brain.dataset),
            'Total semantic statements': self.__brain.count_statements(),
            'Total perspectives': self.__brain.count_statements(),
            'Total sources': self.__brain.count_friends(),
            'Total predicates': len(self.__brain.get_predicates()),
            'Total classes': len(self.__brain.get_classes())
        }

        self.__brain_stats.append(stats)

    def respond(self, capsule, return_br=True):
        """Parses the user input (as a capsule), queries and/or updates the brain
        and returns a reply by consulting the replier.

        params
        str capsule:     input capsule of the user, e.g. a response to a Thought
        bool return_br: whether to return to brain response alongside the reply

        returns: reply to input
        """
        self._turns += 1

        # ERROR
        say, capsule_user, brain_response = None, None, None
        if capsule is None:
            say = choice(SORRY) + " I could not parse that. Can you rephrase?"

        # QUESTION
        elif capsule["utterance_type"] in ["QUESTION", UtteranceType.QUESTION]:
            # Query Brain -> try to answer
            brain_response = self.__brain.query_brain(capsule_for_query(capsule))
            brain_response = brain_response_to_json(brain_response)

            if isinstance(self.__replier, RLReplier):
                self.__replier.reward_thought()

            say, capsule_user = self.__replier.reply_to_question(brain_response), BASE_CAPSULE

        # STATEMENT
        elif capsule["utterance_type"] in ["STATEMENT", UtteranceType.STATEMENT]:
            # Update Brain -> communicate a thought
            brain_response = self.__brain.update(capsule, reason_types=True, create_label=True)
            brain_response = brain_response_to_json(brain_response)

            if isinstance(self.__replier, RLReplier):
                self.__replier.reward_thought()

            say, capsule_user = self._select_rl_thought(brain_response)
            self._score_brain(brain_response)

            capsule_user['chat'] = self._chat_id
            capsule_user['turn'] = self._turns + 1
            capsule_user['author'] = self._speaker
            capsule_user['utterance_type'] = "STATEMENT"
            capsule_user = copy_capsule_context(capsule_user, brain_response['statement'])

        if return_br:
            return say, capsule_user, brain_response
        return say, capsule_user
