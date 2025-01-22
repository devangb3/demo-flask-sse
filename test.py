

def main(arg1, arg2, arg3):
    print(arg1)
    print(arg2)
    print(arg3)
    def inner(here, there, elsewhere):
        print(arg1)
        print(arg2)
        print(arg3)
    return inner