# demo project `hive_mind`: using `agent_tooling`
#### create, read, edit, and delete agents!!!

*Apr 03, 2025*

### > implementing `agent_tooling` in `hive_mind`
- i wanted to demo the `agent_tooling` package in a functional agentic system, and any 
agentic system should have CRUD operations for the agents.
- so in `hive_mind` i've implemented these operations and created several agents that amuse me.
- i did notice that the agent creation workflow could use some tighter workflow orchestration,
so my next effort will be focused on implementing `LangGraph` to tighten this up.

### > create
- iteratively prompt llm to create good code
```python

...
instructions = f"Create a python function with the following requirements: {agent_requirements}"

    agent_code = completions_structured(message=instructions,
                                        response_format=AgentCode,
                                        model="gpt-4o-2024-08-06",
    ).code

    instructions = f''' Update this code: {agent_code} by adding the following:
        1) from the `agent_tooling` module include the `tool` function
        2) add the `@tool` decorator to the main/entry-point function
        Example:
        from agent_tooling import tool
        @tool
        def new_agent_name(message: str) -> Generator[str, None, None]:
        # function code here'''
    
    agent_code = completions_structured(message=instructions,
                                        response_format=AgentCode,
                                        model="gpt-4o-2024-08-06",
    ).code

    instructions = f''' Update this code: {agent_code} by adding the following:
        add a description of the function below the function less than 1024 characters
        1) this description needs to help an llm determine if this is the correct function to call
        for the given request
        2) the description should also help a human understand what the function does'''
    
    agent_code = completions_structured(message=instructions,
                                        response_format=AgentCode,
                                        model="gpt-4o-2024-08-06",
    ).code
...
```

### > read
- list, get by name/description, describe
```python
...
@tool
def list_agents() -> Generator[str, None, None]: 
    """
    List all available agents in the system. This function retrieves the list of agents and formats them into a readable string.
    
    Returns:
        str: A formatted string listing all available agents.
    """

    agents = get_agents() # using the agent_tooling library

    agent_names = [agent.name for agent in agents]

    agent_descriptions = completions_streaming(
            message=f'''Use these agent names: {json.dumps(agent_names)} 
            to list the agents of the HIVE MIND'''
        )

    # stream the response
    for chunk in agent_descriptions:
        yield chunk

@tool
def get_agent_by_name(name: str) -> Agent:
    """
    Get an agent by its name. This function searches for an agent with the specified name and returns it.

    Args:
        name (str): The name of the agent to search for.

    Returns:
        AgentMatches: A list containing the matched agents.
    """

    json_agents = json.dumps(_agents, cls=AgentEncoder)
    matches = completions_structured(
        message=f"Of these agents: {json_agents} return the agent with the name: {name}",
        response_format=AgentMatches
    )
    if not matches:
        return None
    if len(matches.agents) > 1:
        raise ValueError("Multiple agents found with the same name.")
    if len(matches.agents) == 0:
        raise ValueError("No agent found with the given name.")
    # If exactly one agent is found, return it
    return matches.agents[0]
...
```
#### > update
```python
@tool
def update_agent_code(name: str, update_description: str) -> Generator[str, None, None]:
    """
    Update the code of an agent based on a provided description. This function first checks if the requested agent name matches any available agents. If there's an exact match or similar names are found, it loads the current code of the agent, applies the update description to generate new code, and saves the updated code back to the file system.
    
    Args:
        agent_name (str): The name of the agent whose code needs to be updated.
        update_description (str): A detailed description of what changes need to be made in the agent's code.
        
    Returns:
        Generator[str, None, None]: returns either the updated code, or a message if there wasn't an exact match found.
    """
    from agents.agent_read import get_agent_by_name
    agent = get_agent_by_name(name=name)

    code_string = agent.code
    
    # Prepare the update request
    message = f"Update the code of {code_string} based on the following description: {update_description}"
    updated_code = completions_structured(message=message, response_format=AgentCode)

    stream = completions_streaming(
        message=f"Return this code: {updated_code.code} for the agent with the name: {name} along with nicely formatted markdown explaining the code."
    )

    # stream the response
    for chunk in stream:
        yield chunk
    
    # Write the updated code back to the file
    with open(agent.file_path, 'w') as file:
        file.write(updated_code.code)

    # reload the system to get the detail about the edited agent
    discover_tools()
```

#### > delete
- catution: i didn't add any safeguards
```python
@tool
def delete_agent(agent_name: str) -> Generator[str, None, None]:
    """
    This function deletes an unwanted agent by the provided name.
    
    Args:
    - agent_name: The name of the agent to be deleted
    
    Returns:
    A message indicating the success or failure of the operation.
    """
    from agents.agent_read import get_agent_by_name

    try:
        # Locate the agent by name
        agent = get_agent_by_name(agent_name)

        if agent is None:
            return f"Agent named '{agent_name}' not found."

        # Get the file path of the agent
        file_path = agent.file_path
        
        if not os.path.exists(file_path):
            return f"Agent file path '{file_path}' does not exist. Deletion failed."

        # Delete the agent file ensuring no dependencies are left
        os.remove(file_path)

        yield f"Agent '{agent_name}' deleted successfully and system updated."

        discover_tools()

    except Exception as e:
        yield f"An error occurred during deletion: {e}"
```

#### upcoming integrations
- LangGraph:
  -- i've been wanting a way to rely less on the llm to choose the correct order our agents
  work on tasks. also, i want a use human-in-the-loop for some decision making steps. this is
  a perfect opportunity to use LangGraph to accomplish this. i've already done some demo
  projects and proved to myself that this is the way i want to go. now, i just need to pick
  the first task i want to tackle and refactor the tool calling logic. 
- model context protocol (MCP):
  -- there's been a lot of hype around this concept introduced by Anthropic (specifically for 
  Claude), so much so that OpenAI has also started writing an implementation of this. i'm not
  convinced that this trend will last, long-term. the open web-ui project has made a pretty
  good argument that the OpenAPI standard is a better way to accomplish model <-> context
  connections: [why OpenAPI](https://github.com/open-webui/openapi-servers?tab=readme-ov-file#%EF%B8%8F-why-openapi)
  [why mcpo](https://github.com/open-webui/mcpo?tab=readme-ov-file#%EF%B8%8F-mcpo)
  - in any event, i'll try both approaches and see what works best for me.


#### repos
- [hive_mind](https://github.com/danielstewart77/hive_mind?tab=readme-ov-file#agent-tooling-demonstration)

- [agent_tooling](https://github.com/danielstewart77/agent_tooling?tab=readme-ov-file#agent-tooling)

- [PyPI](https://pypi.org/project/agent-tooling/)

#### contact
- [LinkedIn](https://www.linkedin.com/in/danielstewart-ai/)
