from os import path, getcwd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import torch
from torch import nn
import pandas as pd
import matplotlib.pyplot as plt
from dataset_loader import AbstractsDataset
from metrics import calculate_metrics_mean, Metrics


DATA_DIR = path.join(getcwd(), 'data', 'processed')
VOCAB_SIZE = None
DATASET = 'top5'
BATCH_SIZE = 2048
LEARNING_RATE = 1e-3
HIDDEN_IN = 1024
HIDDEN_OUT = 512
EPOCHS = 20


def main():
    # load dataset
    fname = path.join(DATA_DIR, DATASET + '.csv')
    df = pd.read_csv(fname, quotechar='"', dtype=str)
    vectorizer = TfidfVectorizer(encoding='ascii', max_features=VOCAB_SIZE)
    X = vectorizer.fit_transform(df['abstract'])
    y = np.array([list(map(int, mask)) for mask in df['keywords']],
                 dtype='uint8')

    # train-validate-test split
    inds = np.random.permutation(df.shape[0])
    i1, i2 = (df.shape[0] * np.array([0.9, 0.95])).astype(int)
    train_dataset = AbstractsDataset(X[inds[:i1]], y[inds[:i1]], BATCH_SIZE)
    val_dataset = AbstractsDataset(X[inds[i1:i2]], y[inds[i1:i2]], BATCH_SIZE)
    test_dataset = AbstractsDataset(X[inds[i2:]], y[inds[i2:]], BATCH_SIZE)

    # choose device and initialize model
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = Model(
        num_features=X.shape[1],
        num_labels=y.shape[1],
        shape_hidden=(HIDDEN_IN, HIDDEN_OUT)
    )
    model = model.to(device)

    # train model
    train_losses, val_losses, train_metrics, val_metrics = train(
        model=model,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        device=device,
        epochs=EPOCHS,
        lr=LEARNING_RATE
    )

    # plot results
    plt.figure()
    plt.plot(train_losses)
    plt.plot(val_losses)
    plt.xlabel('Epoch')
    plt.ylabel('Loss')

    plt.figure()
    plt.plot(train_metrics.accuracy)
    plt.plot(val_metrics.accuracy)
    plt.xlabel('Epoch')
    plt.ylabel('Mean accuracy')

    plt.figure()
    plt.plot(train_metrics.precision)
    plt.plot(val_metrics.precision)
    plt.xlabel('Epoch')
    plt.ylabel('Mean precision')

    plt.figure()
    plt.plot(train_metrics.recall)
    plt.plot(val_metrics.recall)
    plt.xlabel('Epoch')
    plt.ylabel('Mean recall')

    plt.show()


class Model(nn.Module):
    """
    Neural net with a single hidden layer.
    """
    def __init__(self, num_features, num_labels, shape_hidden=(1024, 512)):
        super().__init__()
        self.flatten = nn.Flatten()
        self.stack = nn.Sequential(
            nn.Linear(num_features, shape_hidden[0]),
            nn.ReLU(),
            nn.Linear(shape_hidden[0], shape_hidden[1]),
            nn.ReLU(),
            nn.Linear(shape_hidden[1], num_labels),
            nn.Sigmoid()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.stack(x)


def train(model, train_dataset, val_dataset, device, epochs=20, lr=1e-3):
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    train_losses = np.zeros(epochs)
    train_metrics = np.zeros((epochs, 3))
    val_losses = np.zeros_like(train_losses)
    val_metrics = np.zeros_like(train_metrics)
    loss_function = nn.BCELoss()

    for i in range(epochs):
        print(f'Epoch {i}')

        # train loop
        loss, acc, prec, rec = single_pass(
            model=model,
            dataset=train_dataset,
            device=device,
            loss_function=loss_function,
            optimizer=optimizer
        )
        print(f'Train: loss = {loss:.3f},', end=' ')
        print(f'acc = {acc:.3f}, prec = {prec:.3f}, rec = {rec:.3f}')
        train_losses[i] = loss
        train_metrics[i, :] = acc, prec, rec

        # validation loop
        with torch.no_grad():
            loss, acc, prec, rec = single_pass(
                model=model,
                dataset=val_dataset,
                device=device,
                loss_function=loss_function,
                optimizer=None
            )
        print(f'Validation: loss = {loss:.3f},', end=' ')
        print(f'acc = {acc:.3f}, prec = {prec:.3f}, rec = {rec:.3f}')
        val_losses[i] = loss
        val_metrics[i, :] = acc, prec, rec
        print()

    train_metrics = Metrics(
        accuracy=train_metrics[:, 0],
        precision=train_metrics[:, 1],
        recall=train_metrics[:, 2]
    )
    val_metrics = Metrics(
        accuracy=val_metrics[:, 0],
        precision=val_metrics[:, 1],
        recall=val_metrics[:, 2]
    )

    return train_losses, val_losses, train_metrics, val_metrics


def single_pass(model, dataset, device, loss_function, optimizer=None):
    # train loop
    losses = []
    accuracies = []
    precision_values = []
    recall_values = []
    batch_sizes = []
    for X_j, y_j in dataset:
        # forward loop
        X_j = torch.tensor(X_j, dtype=torch.float32, device=device)
        y_j = torch.tensor(y_j, dtype=torch.float32, device=device)
        output = model.forward(X_j)
        loss = loss_function(output, y_j)
        # evaluate and save metrics
        losses.append(loss.item())
        predicted = np.round(output.cpu().detach().numpy()).astype('uint8')
        m = calculate_metrics_mean(
            predicted, y_j.cpu().numpy().astype('uint8'))
        accuracies.append(m.accuracy)
        precision_values.append(m.precision)
        recall_values.append(m.recall)
        batch_sizes.append(X_j.shape[0])

        if optimizer is not None:
            # backpropagation
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    batch_sizes = np.array(batch_sizes)
    num_samples = np.sum(batch_sizes)
    loss = np.sum(np.array(losses) * batch_sizes) / num_samples
    accuracy = np.sum(np.array(accuracies) * batch_sizes) / num_samples
    precision = np.sum(np.array(precision_values) * batch_sizes) / num_samples
    recall = np.sum(np.array(recall_values * batch_sizes)) / num_samples
    return loss, accuracy, precision, recall


if __name__ == '__main__':
    main()
