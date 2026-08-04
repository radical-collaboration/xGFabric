# tasks/

- Each directory here belongs to its own task. 
- The code / binaries to execute the task.

What does **not** belong here:
- The actual dag (the dependencies...)
- Resource allocation
- Coordinator
- etc...

Concept: separation between tasks (what containers are meant for) but not using
containers
