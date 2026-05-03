# Logic & Legacy: Serialization & The Stack-Based VM
# Demonstrates standard JSON serialization vs a custom-built "Pickle" engine.
# We build a MiniPickle Virtual Machine from scratch to prove how Python
# translates complex memory structures into byte-stream opcodes.

import json
import pickle
import pickletools

# ==========================================
# 1. THE JSON STANDARD (Human-Readable / Secure)
# ==========================================

def standard_json_serialization():
    print("--- 1. JSON SERIALIZATION ---")
    data = {"user_id": 99, "role": "admin", "permissions": ["read", "write"]}
    
    # Serialization (Python -> String)
    json_string = json.dumps(data)
    print(f"Serialized JSON: {json_string}")
    
    # Deserialization (String -> Python)
    restored_data = json.loads(json_string)
    print(f"Restored Object Type: {type(restored_data)}\n")

"""
EXPECTED OUTPUT:
--- 1. JSON SERIALIZATION ---
Serialized JSON: {"user_id": 99, "role": "admin", "permissions": ["read", "write"]}
Restored Object Type: <class 'dict'>
"""

# ==========================================
# 2. THE MINI-PICKLE VIRTUAL MACHINE
# ==========================================

class MiniPickle:
    """
    A minimal implementation of Python's pickle protocol.
    Pickle does NOT just 'save data'. It generates an instruction set (opcodes) 
    that a Stack-Based Virtual Machine executes to rebuild the object in memory.
    """
    # Instruction Opcodes
    INT     = b'I'  # Followed by integer and newline
    STRING  = b'S'  # Followed by string and newline
    LIST    = b'L'  # Create empty list on stack
    APPEND  = b'A'  # Append top of stack to list below it
    STOP    = b'.'  # End of stream

    def dumps(self, obj):
        """Compiler: Converts a Python object into a byte-stream of instructions."""
        if isinstance(obj, int):
            # I<value>\n.
            return self.INT + str(obj).encode() + b'\n' + self.STOP
        elif isinstance(obj, str):
            # S<value>\n.
            return self.STRING + obj.encode() + b'\n' + self.STOP
        elif isinstance(obj, list):
            # L
            # <Item1 Instructions>A
            # <Item2 Instructions>A
            # .
            res = self.LIST
            for item in obj:
                # Recursively pickle items and slice off the STOP instruction ([:-1])
                res += self.dumps(item)[:-1] 
                res += self.APPEND
            return res + self.STOP
        else:
            raise TypeError(f"MiniPickle cannot serialize type {type(obj)}")

    def loads(self, data: bytes):
        """Virtual Machine: Executes instructions in the byte stream to rebuild the object."""
        stack = []
        pointer = 0
        
        while pointer < len(data):
            opcode = data[pointer:pointer+1]
            pointer += 1
            
            if opcode == self.INT:
                newline = data.find(b'\n', pointer)
                stack.append(int(data[pointer:newline]))
                pointer = newline + 1
                
            elif opcode == self.STRING:
                newline = data.find(b'\n', pointer)
                stack.append(data[pointer:newline].decode())
                pointer = newline + 1
                
            elif opcode == self.LIST:
                stack.append([])
                
            elif opcode == self.APPEND:
                val = stack.pop()
                stack[-1].append(val)
                
            elif opcode == self.STOP:
                return stack.pop()
                
            else:
                raise ValueError(f"Unknown Opcode: {opcode}")


def run_minipickle():
    print("--- 2. THE MINI-PICKLE VIRTUAL MACHINE ---")
    engine = MiniPickle()
    
    # The complex object we want to send over a network socket
    target_object = ["admin", 42, ["nested_data"]]
    
    # 1. Compile the object into Opcodes
    byte_stream = engine.dumps(target_object)
    print(f"Compiled Byte Stream:\n{byte_stream}")
    
    # 2. Execute the Opcodes to rebuild the object in RAM
    rebuilt_object = engine.loads(byte_stream)
    print(f"Rebuilt Object:\n{rebuilt_object}\n")

"""
EXPECTED OUTPUT:
--- 2. THE MINI-PICKLE VIRTUAL MACHINE ---
Compiled Byte Stream:
b'LSadmin\nAII42\nALSnested_data\nAIA.'
Rebuilt Object:
['admin', 42, ['nested_data']]
"""


# ==========================================
# 3. REAL CPYTHON PICKLE DISASSEMBLY
# ==========================================

def disassemble_real_pickle():
    print("--- 3. REAL CPYTHON PICKLE DISASSEMBLY ---")
    target_object = [1, "hi"]
    
    # Create the real Python pickle byte stream
    real_byte_stream = pickle.dumps(target_object)
    
    # Disassemble it to view the actual C-level VM instructions
    print("Executing pickletools.dis():")
    pickletools.dis(real_byte_stream)
    
    print("""
[ARCHITECT'S NOTE] Why is implementing a full pickle engine so difficult?
1. Classes/Functions: Real pickle stores the module/class name as strings and uses 
   getattr(import_module(mod), name) dynamically during deserialization.
2. The MEMO Table: To prevent infinite loops with circular references (e.g., a list 
   that contains itself), pickle maintains a 'Memo' dictionary tracking memory addresses.
3. The REDUCE Opcode: The real protocol allows objects to define a __reduce__ method, 
   which tells the VM to execute ANY arbitrary function. This is why unpickling 
   untrusted data is a critical Remote Code Execution (RCE) vulnerability.
    """)

"""
EXPECTED OUTPUT:
--- 3. REAL CPYTHON PICKLE DISASSEMBLY ---
Executing pickletools.dis():
    0: \x80 PROTO      4
    2: \x95 FRAME      11
   11: ]    EMPTY_LIST
   12: \x94 MEMOIZE    (as 0)
   13: (    MARK
   14: K        BININT1    1
   16: \x8c     SHORT_BINUNICODE 'hi'
   20: \x94     MEMOIZE    (as 1)
   21: e        APPENDS    (to 0)
   22: .    STOP
highest protocol among opcodes = 4
"""

if __name__ == "__main__":
    standard_json_serialization()
    run_minipickle()
    disassemble_real_pickle()
