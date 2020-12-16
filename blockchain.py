import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4
import random
import requests
from flask import Flask, jsonify, request


class Blockchain:
    def __init__(self):
        #transient list to add contents to chain
        self.current_transactions = []
        #overall list for tabulation purposes
        self.overall_transactions = []
        self.chain = []
        self.ballot = set('')
        self.nodes = set()

        # Create the genesis block
        self.new_block(previous_hash='1', proof=100)

    def register_node(self, address, govt):

        parsed_url = urlparse(address)
        if parsed_url.netloc:
            if govt:
                self.nodes.add('g' + parsed_url.netloc)
            else:
                self.nodes.add('c' + parsed_url.netloc)
        elif parsed_url.path:
            # Accepts an URL without scheme like '192.168.0.5:5000'.
            if govt:
                self.nodes.add('g' + parsed_url.path)
            else:
                self.nodes.add('c' + parsed_url.path)
        else:
            raise ValueError('Invalid URL')

    def add_candidate(self, name):
        self.ballot.add(name)

    def valid_chain(self, chain):

        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")
            # Check that the hash of the block is correct
            last_block_hash = self.hash(last_block)
            if block['previous_hash'] != last_block_hash:
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block['proof'], block['proof'], last_block_hash):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):

        neighbours = self.nodes
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        return False

    def new_block(self, proof, previous_hash):
        """
        Create a new Block in the Blockchain
        :param proof: The proof given by the Proof of Work algorithm
        :param previous_hash: Hash of previous Block
        :return: New Block
        """

        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }

        # Reset the current list of transactions
        self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount, name):
        """
        Creates a new transaction to go into the next mined Block
        :param sender: Address of the Sender
        :param recipient: Address of the Recipient
        :param amount: Amount
        :param name: Name of who is being voted for
        :return: The index of the Block that will hold this transaction

        Conditional functions as a pseudo smart contract
        FOR EVERY TRANSACTION:
            Validates Civilian -> Government
            Validates exactly 1 token transferred
            Validates vote exists in ballot options (does not support write-ins)
            Validates both transacting nodes are registered
            Validates person has not voted before (redundancy check)
        """

        sregistered = False
        rregistered = False
        firstvote = True

        for node in self.nodes:
            if sender == node:
                sregistered = True
            elif recipient == node:
                rregistered = True

        for tx in self.overall_transactions:
            if tx['sender'] == sender:
                firstvote = False

        if sender[0]=='c' and recipient[0]=='g' and amount==1 and name in self.ballot and sregistered and rregistered and firstvote:
            # hash values of sender and recipient to preserve anonymity
            # keep first letter of address to differentiate civillian and government nodes
            sndr = sender[0] + hashlib.sha256(sender[1:].encode()).hexdigest()
            rcpt = recipient[0] + hashlib.sha256(recipient[1:].encode()).hexdigest()

            self.current_transactions.append({
                'sender': sndr,
                'recipient': rcpt,
                'amount': amount,
                'name': name
            })
            #keeps track of total transactions for tabulation purposes, as current transactions is per block basis
            #true implementation would not need to keep this data, especially unhashed
            self.overall_transactions.append({
                'sender': sender,
                'recipient': recipient,
                'amount': amount,
                'name': name
            })

            #adds transaction to a random block in the future to add to identity protection
            randomwaittime = random.randint(1,3)
            index = self.last_block['index'] + randomwaittime

            return f'Vote will be added to block {index}'
        else:
            return 'Error: invalid transaction. Must be from civilian to government node. Must be exactly 1 token. Name must be on ballot. Vote will not be sent'


    @property
    def last_block(self):
        return self.chain[-1]

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block
        :param block: Block
        """

        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self, last_block):
        """
        Simple Proof of Work Algorithm:
        :param last_block: <dict> last Block
        :return: <int>
        """

        last_proof = last_block['proof']
        last_hash = self.hash(last_block)

        proof = 0
        while self.valid_proof(last_proof, proof, last_hash) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof, last_hash):
        """
        Validates the Proof
        :param last_proof: <int> Previous Proof
        :param proof: <int> Current Proof
        :param last_hash: <str> The hash of the Previous Block
        :return: <bool> True if correct, False if not.
        """

        guess = f'{last_proof}{proof}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"


# Instantiate the Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the Blockchain
blockchain = Blockchain()

@app.route('/add_candidate', methods=["POST"])
def add():
    values = request.get_json(force=True)

    required = ['name']
    if not all(k in values for k in required):
        return 'Enter a name', 400

    blockchain.add_candidate(values['name'])

    candidate = values['name']
    response = f'Candidate {candidate} added'
    return jsonify(response), 200

@app.route('/mine', methods=['GET'])
def mine():
    # We run the proof of work algorithm to get the next proof...
    last_block = blockchain.last_block
    proof = blockchain.proof_of_work(last_block)


    # Forge the new Block by adding it to the chain
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)


    #In theory, only government nodes will be able to mine in the form of CBFT consensus.
    #In this simulation, net behaviour is similar to that of mining
    #For this simulation, we pretend every user logged in is a government node

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200

@app.route('/tabulate', methods=['GET'])
def tabulate():

    total = []

    for transaction in blockchain.overall_transactions:
        if transaction['sender'] != '0':
            total.append(transaction)


    ballot = blockchain.ballot

    #creates dictionary for each name on ballot
    ballotdict = {}
    for name in ballot:
        ballotdict[name] = 0

    #adds one to the corresponding candidate for each appearance of their name in transaction list
    #Simplistic; better suited to small elections given runtime
    for vote in total:
        ballotdict[vote['name']] =+ 1


    #reports vote totals
    message = ''

    for key in ballotdict:
        message = message + f'{key}: {ballotdict[key]} vote(s). '

    response = {'message': f'{message}'}

    return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json(force=True)

    # Check that the required fields are in the POST'ed data
    required = ['sender', 'recipient', 'amount', 'name']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # Create a new Transaction
    tx = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'], values['name'])

    return jsonify(tx), 201


@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json(force=True)

    required = ['address', 'type']
    if not all(k in values for k in required):
        return 'Missing values', 400

    #store nodes as a tuple
    node = (values['address'], values['type'])
    if node is None:
        return "Error: Please supply a valid node // 'address', 'type'", 400

    (addr, typ) = node
    blockchain.register_node(addr, typ)
    # give 1 token exactly to each registered node
    blockchain.new_transaction("0", addr, 1, '')

    response = {
        'message': 'New node has been added and given 1 token',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200


if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    port = args.port

    app.run(host='0.0.0.0', port=port)