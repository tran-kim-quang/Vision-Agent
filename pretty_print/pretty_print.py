from langchain_core.messages import convert_to_messages

def pretty_print(message, indent=False):
    pretty_msg = message.pretty_repr(html=False)
    if not indent:
        print(pretty_msg)
        return
    indented = "\n".join("\t" + line for line in pretty_msg.split("\n"))
    print(indented)

def pretty_print_messages(update, last_message=False):
    is_subgraph = False
    if isinstance(update, tuple):
        ns, update = update
        if len(ns) == 0:
            return
        graph_id = ns[-1].split(":")[0]
        print(f"Update for graph: {graph_id} \n")
        is_subgraph = True
    
    for node_name, node_update in update.items():
        update_label = f"Update from node {node_name}:\n"
        if is_subgraph:
            update_label = f"\t{update_label}"
        print(update_label)

        messages = convert_to_messages(node_update["messages"])
        if last_message:
            messages = [messages[-1]]
        for msg in messages:
            pretty_print(msg, indent=is_subgraph)
        print("\n")