import streamlit as st

st.set_page_config(page_title="ToDo List", page_icon="📝")

if 'todo_list' not in st.session_state:
    st.session_state.todo_list = []

st.title("📝 Список задач")

new_todo = st.text_input("Добавить задачу:")
if st.button("Добавить"):
    if new_todo:
        st.session_state.todo_list.append({"task": new_todo, "done": False})
        st.rerun()

st.write("---")
for i, item in enumerate(st.session_state.todo_list):
    col_t, col_b = st.columns([4, 1])
    done = col_t.checkbox(item['task'], value=item['done'], key=f"todo_{i}")
    st.session_state.todo_list[i]['done'] = done
    if col_b.button("❌", key=f"del_{i}"):
        st.session_state.todo_list.pop(i)
        st.rerun()
