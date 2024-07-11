from typing import Callable, Optional, Type

import instructor
from pydantic import BaseModel, Field
from rich.json import JSON

from atomic_agents.lib.components.agent_memory import AgentMemory
from atomic_agents.lib.components.system_prompt_generator import SystemPromptContextProviderBase, SystemPromptGenerator


class BaseAgentIO(BaseModel):
    """
    Base class for input and output schemas for chat agents.
    """

    def __str__(self):
        return self.model_dump_json()

    def __rich__(self):
        json_str = self.model_dump_json()
        return JSON(json_str)


class BaseAgentInputSchema(BaseAgentIO):
    chat_message: str = Field(
        ...,
        description="The chat message sent by the user to the assistant.",
    )

    class Config:
        title = "BaseAgentInputSchema"
        description = "This schema represents the user input message exchanged between the user and the chat agent."
        json_schema_extra = {
            "title": title,
            "description": description,
        }


class BaseAgentOutputSchema(BaseAgentIO):
    chat_message: str = Field(
        ...,
        description=(
            "The chat message exchanged between the user and the chat agent. "
            "This contains the markdown-enabled response generated by the chat agent."
        ),
    )

    class Config:
        title = "BaseAgentOutputSchema"
        description = "This schema represents the response message exchanged between the user and the chat agent."
        json_schema_extra = {
            "title": title,
            "description": description,
        }


class BaseAgentConfig(BaseModel):
    client: instructor.client.Instructor = Field(..., description="Client for interacting with the language model.")
    model: str = Field("gpt-3.5-turbo", description="The model to use for generating responses.")
    memory: Optional[AgentMemory] = Field(None, description="Memory component for storing chat history.")
    system_prompt_generator: Optional[SystemPromptGenerator] = Field(
        None, description="Component for generating system prompts."
    )
    input_schema: Optional[Type[BaseModel]] = Field(None, description="The schema for the input data.")
    output_schema: Optional[Type[BaseModel]] = Field(None, description="The schema for the output data.")
    
    class Config:
        arbitrary_types_allowed = True


class BaseAgent:
    """
    Base class for chat agents.

    This class provides the core functionality for handling chat interactions, including managing memory,
    generating system prompts, and obtaining responses from a language model.

    Attributes:
        input_schema (Type[BaseAgentIO]): Schema for the input data.
        output_schema (Type[BaseAgentIO]): Schema for the output data.
        client: Client for interacting with the language model.
        model (str): The model to use for generating responses.
        memory (AgentMemory): Memory component for storing chat history.
        system_prompt_generator (SystemPromptGenerator): Component for generating system prompts.
        initial_memory (AgentMemory): Initial state of the memory.
    """

    input_schema = BaseAgentInputSchema
    output_schema = BaseAgentOutputSchema

    def __init__(self, config: BaseAgentConfig):
        """
        Initializes the BaseAgent.

        Args:
            config (BaseAgentConfig): Configuration for the chat agent.
        """
        self.input_schema = config.input_schema or self.input_schema
        self.output_schema = config.output_schema or self.output_schema
        self.client = config.client
        self.model = config.model
        self.memory = config.memory or AgentMemory()
        self.system_prompt_generator = config.system_prompt_generator or SystemPromptGenerator()
        self.initial_memory = self.memory.copy()
        self.current_user_input = None

    def reset_memory(self):
        """
        Resets the memory to its initial state.
        """
        self.memory = self.initial_memory.copy()

    def get_response(self, response_model=None) -> Type[BaseModel]:
        """
        Obtains a response from the language model.

        Args:
            response_model (Type[BaseModel], optional):
                The schema for the response data. If not set, self.output_schema is used.

        Returns:
            Type[BaseModel]: The response from the language model.
        """
        if response_model is None:
            response_model = self.output_schema

        messages = [
            {
                "role": "system",
                "content": self.system_prompt_generator.generate_prompt(),
            }
        ] + self.memory.get_history()
        response = self.client.chat.completions.create(model=self.model, messages=messages, response_model=response_model)
        return response

    def run(self, user_input: Optional[Type[BaseAgentIO]] = None) -> Type[BaseAgentIO]:
        """
        Runs the chat agent with the given user input.

        Args:
            user_input (Optional[Type[BaseAgentIO]]): The input from the user. If not provided, skips adding to memory.

        Returns:
            Type[BaseAgentIO]: The response from the chat agent.
        """
        if user_input:
            self.current_user_input = user_input
            self.memory.add_message("user", str(user_input))

        response = self.get_response(response_model=self.output_schema)
        self.memory.add_message("assistant", str(response))
        
        return response

    def get_context_provider(self, provider_name: str) -> Type[SystemPromptContextProviderBase]:
        """
        Retrieves a context provider by name.

        Args:
            provider_name (str): The name of the context provider.

        Returns:
            SystemPromptContextProviderBase: The context provider if found.

        Raises:
            KeyError: If the context provider is not found.
        """
        if provider_name not in self.system_prompt_generator.system_prompt_info.context_providers:
            raise KeyError(f"Context provider '{provider_name}' not found.")
        return self.system_prompt_generator.system_prompt_info.context_providers[provider_name]

    def register_context_provider(self, provider_name: str, provider: SystemPromptContextProviderBase):
        """
        Registers a new context provider.

        Args:
            provider_name (str): The name of the context provider.
            provider (SystemPromptContextProviderBase): The context provider instance.
        """
        self.system_prompt_generator.system_prompt_info.context_providers[provider_name] = provider

    def unregister_context_provider(self, provider_name: str):
        """
        Unregisters an existing context provider.

        Args:
            provider_name (str): The name of the context provider to remove.
        """
        if provider_name in self.system_prompt_generator.system_prompt_info.context_providers:
            del self.system_prompt_generator.system_prompt_info.context_providers[provider_name]
        else:
            raise KeyError(f"Context provider '{provider_name}' not found.")